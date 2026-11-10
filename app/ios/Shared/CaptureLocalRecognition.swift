import CoreGraphics
import Foundation
import ImageIO
import Vision
import onnxruntime_objc

/// State belongs to the capture queue. Only bounded JPEGs cross to the inference queue.
final class CaptureLocalRecognition {
  private enum Phase: String { case ocr, buttons, finished }
  private let queue = DispatchQueue(label: "screen.local-recognition", qos: .utility)
  private let buttonModel = CaptureButtonModel()
  private var phase = Phase.ocr
  private var epoch: Int64 = 0
  private var lastFrame: Int64 = 0
  private var count = 0
  private var run = UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased()
  private var started = 0.0, progress = 0.0
  private var inFlight = false
  private var rows = [String: (frame: Int64, fields: [String: Any])]()

  func offer(_ jpeg: Data, stamp: Int64, now: Double, callbackQueue: DispatchQueue) {
    guard phase != .finished, stamp > lastFrame, (0...2.5).contains(now - Double(stamp) / 1e9) else { return }
    if epoch == 0 {
      epoch = stamp
      lastFrame = stamp
      started = now
      progress = now
      return
    }
    tick(now)
    guard phase != .finished, !inFlight, stamp > lastFrame else { return }
    inFlight = true
    lastFrame = stamp
    let phase = self.phase, run = self.run
    queue.async {
      let output: [String: Any]? = autoreleasepool {
        try? self.recognize(phase, jpeg: jpeg)
      }
      callbackQueue.async {
        self.inFlight = false
        let completedAt = ProcessInfo.processInfo.systemUptime
        self.tick(completedAt)
        guard self.phase == phase, self.run == run else { return }
        guard var output = output else { self.advance("error", now: completedAt); return }
        self.count += 1
        self.progress = completedAt
        output["source"] = phase.rawValue
        output["run"] = run
        output["epoch"] = String(self.epoch)
        output["frame"] = String(stamp)
        output["count"] = self.count
        output["state"] = "running"
        self.rows[phase.rawValue] = (stamp, output)
        if self.count == 10 { self.advance("done", now: completedAt) }
      }
    }
  }

  func tick(_ now: Double) {
    guard phase != .finished, epoch != 0 else { return }
    if now - started >= 90 { advance("timeout", now: now) }
    else if now - progress >= 12 { advance("frame_timeout", now: now) }
  }

  private func advance(_ reason: String, now: Double) {
    rows[phase.rawValue]?.fields["state"] = reason
    phase = phase == .ocr ? .buttons : .finished
    run = UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased()
    started = now
    progress = now
    count = 0
  }

  func stop() {
    phase = .finished
    rows.removeAll()
  }

  func payload(now: Double) -> Data {
    let latest = rows.values.compactMap { row -> [String: Any]? in
      let age = (now - Double(row.frame) / 1e9) * 1000
      guard (0...12000).contains(age) else { return nil }
      var fields = row.fields
      fields["ageMs"] = Int(age)
      return fields
    }
    return (try? JSONSerialization.data(withJSONObject: [
      "v": 1, "platform": "ios", "results": latest
    ])) ?? Data()
  }

  private func recognize(_ phase: Phase, jpeg: Data) throws -> [String: Any] {
    switch phase {
    case .ocr:
      let request = VNRecognizeTextRequest()
      request.recognitionLevel = .accurate
      request.recognitionLanguages = ["zh-Hans", "en-US"]
      try VNImageRequestHandler(data: jpeg).perform([request])
      let text = (request.results ?? []).prefix(12).compactMap {
        $0.topCandidates(1).first?.string
      }.joined(separator: "\n")
      return ["text": String(String.UnicodeScalarView(text.unicodeScalars.prefix(480)))]
    case .buttons:
      return ["boxes": try buttonModel.count(jpeg)]
    case .finished:
      return [:]
    }
  }
}

private final class CaptureButtonModel {
  private let side = 320
  private let anchors = 2100
  private var session: ORTSession?
  private var environment: ORTEnv?

  private func load() throws -> ORTSession {
    if let session = session { return session }
    let bundle = Bundle.main.bundleURL
    let app = bundle.pathExtension == "appex" ? bundle.deletingLastPathComponent().deletingLastPathComponent() : bundle
    let model = app.appendingPathComponent("Frameworks/App.framework/flutter_assets/assets/bt_v10_int8.onnx")
    let environment = try ORTEnv(loggingLevel: .error)
    let options = try ORTSessionOptions()
    try options.setIntraOpNumThreads(1)
    let session = try ORTSession(env: environment, modelPath: model.path, sessionOptions: options)
    self.environment = environment
    self.session = session
    return session
  }

  func count(_ jpeg: Data) throws -> Int {
    let session = try load()
    guard let imageSource = CGImageSourceCreateWithData(jpeg as CFData, nil),
          let image = CGImageSourceCreateImageAtIndex(imageSource, 0, nil),
          let input = try session.inputNames().first, let output = try session.outputNames().first,
          let context = CGContext(data: nil, width: side, height: side, bitsPerComponent: 8,
                                  bytesPerRow: side * 4, space: CGColorSpaceCreateDeviceRGB(),
                                  bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue),
          let pixels = context.data?.assumingMemoryBound(to: UInt8.self) else { throw ModelError.invalid }
    context.interpolationQuality = .low
    context.draw(image, in: CGRect(x: 0, y: 0, width: side, height: side))
    let area = side * side
    let bytes = NSMutableData(length: 3 * area * MemoryLayout<Float>.size)!
    let floats = bytes.mutableBytes.assumingMemoryBound(to: Float.self)
    for pixel in 0..<area {
      floats[pixel] = Float(pixels[4 * pixel]) / 255
      floats[pixel + area] = Float(pixels[4 * pixel + 1]) / 255
      floats[pixel + 2 * area] = Float(pixels[4 * pixel + 2]) / 255
    }
    let tensor = try ORTValue(tensorData: bytes, elementType: .float, shape: [1, 3, 320, 320])
    guard let result = try session.run(withInputs: [input: tensor], outputNames: [output], runOptions: nil)[output] else {
      throw ModelError.invalid
    }
    let shape = try result.tensorTypeAndShapeInfo()
    let data = try result.tensorData()
    guard shape.elementType == .float, shape.shape == [1, 5, 2100],
          data.length == 5 * anchors * MemoryLayout<Float>.size else { throw ModelError.invalid }
    let values = data.bytes.assumingMemoryBound(to: Float.self)
    var candidates = [(box: CGRect, score: Float)]()
    let bounds = CGRect(x: 0, y: 0, width: side, height: side)
    for i in 0..<anchors {
      let score = values[4 * anchors + i]
      let x = CGFloat(values[i]), y = CGFloat(values[anchors + i])
      let w = CGFloat(values[2 * anchors + i]), h = CGFloat(values[3 * anchors + i])
      guard [x, y, w, h].allSatisfy({ $0.isFinite }), (0...1).contains(score) else { throw ModelError.invalid }
      guard score >= 0.45, w > 0, h > 0 else { continue }
      let box = CGRect(x: x - w / 2, y: y - h / 2, width: w, height: h).intersection(bounds)
      if !box.isEmpty { candidates.append((box, score)) }
    }
    var kept = [CGRect]()
    for candidate in candidates.sorted(by: { $0.score > $1.score }) {
      let box = candidate.box
      if kept.contains(where: { other in
        let intersection = box.intersection(other)
        guard !intersection.isEmpty else { return false }
        let overlap = intersection.width * intersection.height
        return overlap / (box.width * box.height + other.width * other.height - overlap) > 0.45
      }) { continue }
      kept.append(box)
      if kept.count == 100 { break }
    }
    return kept.count
  }

  private enum ModelError: Error { case invalid }
}
