import Foundation
import CoreMedia
import CoreVideo
import CoreImage
import ImageIO

/// Shared memory-only uploader. Capture adapters own the real system consent and stream.
final class CapturePipeline {
  private let worker = DispatchQueue(label:"screen.broadcast")
  private let lock = NSLock()
  private var pending: (sample: CMSampleBuffer, orientation: UInt32, capturedAt: CMTime)?
  private var accepting = false
  private var onStopped: ((String) -> Void)?
  private var scheduled = false
  private var grantID = "", ticket = "", barrier = ""
  private var endpoint: URL?
  private var sequence = 0
  private var afterResponse = CMTime.zero
  private var geometry: (Int,Int,UInt32)?
  private var lastFrame = 0.0, fastUntil = 0.0, lastPoll = 0.0
  private var live = false, polling = false
  private var heartbeat: DispatchSourceTimer?
  private var upload: BoundedRequest?, statusRequest: BoundedRequest?, windowRequest: BoundedRequest?
  private var windowInFlight = false
  private var preparationFence = CapturePreparationFence()
  private var taskStatus = ""
  private let context = CIContext(options:[.cacheIntermediates:false])
  func start(onStarted: @escaping () -> Void = {}, onStopped: @escaping (String) -> Void) {
    worker.async {
      self.onStopped = onStopped
      guard let grant = CaptureContract.validGrant(), let id = grant["id"] as? String, let ticket = grant["ticket"] as? String else { self.end("授权已过期，请重新共享"); return }
      self.grantID = id; self.ticket = ticket; self.endpoint = CaptureContract.base; self.live = true
      self.lock.lock(); self.accepting = true; self.lock.unlock()
      self.publish("共享中，等待任务")
      let timer = DispatchSource.makeTimerSource(queue:self.worker); self.heartbeat = timer
      timer.schedule(deadline:.now(),repeating:1); timer.setEventHandler { [weak self] in self?.tick() }; timer.resume()
      DispatchQueue.main.async { onStarted() }
    }
  }
  func submit(_ sampleBuffer: CMSampleBuffer, orientation: UInt32, capturedAt: CMTime) {
    guard CMSampleBufferDataIsReady(sampleBuffer), capturedAt.isValid, capturedAt.isNumeric else { return }
    lock.lock(); guard accepting else { lock.unlock(); return }
    pending = (sampleBuffer,orientation,capturedAt)
    if scheduled { lock.unlock(); return }; scheduled = true; lock.unlock()
    worker.async { self.drain() }
  }
  func stop(_ reason: String, notify: Bool = true) { worker.async { if !notify { self.onStopped = nil }; self.end(reason) } }
  private func drain() {
    lock.lock(); let frame = pending; pending = nil; lock.unlock()
    guard live, valid(), let frame = frame else { releaseSlot(); return }
    let sample = frame.sample
    let now = ProcessInfo.processInfo.systemUptime
    guard now - lastFrame >= (now < fastUntil ? 0.1 : 0.8), CMTimeCompare(frame.capturedAt,afterResponse) > 0,
      let buffer = CMSampleBufferGetImageBuffer(sample) else { releaseSlot(); return }
    let orientation = frame.orientation
    let w = CVPixelBufferGetWidth(buffer), h = CVPixelBufferGetHeight(buffer)
    if let old = geometry, old.0 != w || old.1 != h || old.2 != orientation { end("屏幕方向已改变，请重新共享"); releaseSlot(); return }
    geometry = (w,h,orientation); lastFrame = now
    autoreleasepool {
      let oriented = CIImage(cvPixelBuffer:buffer).oriented(forExifOrientation:Int32(orientation))
      let bounds = oriented.extent
      let factor = min(1,min(720 / bounds.width,1280 / bounds.height))
      let image = oriented.transformed(by:CGAffineTransform(scaleX:factor,y:factor))
      guard let bytes = context.jpegRepresentation(of:image,colorSpace:CGColorSpaceCreateDeviceRGB(),options:[CIImageRepresentationOption(rawValue: kCGImageDestinationLossyCompressionQuality as String):0.7]), bytes.count <= 524288 else { end("画面编码超限，请重新共享"); releaseSlot(); return }
      sequence += 1
      let headers = ["Content-Type":"image/jpeg","X-Screen-Platform":"ios","X-Screen-Sequence":String(sequence),"X-Screen-Barrier":barrier,"X-Screen-Native-Width":String(Int(bounds.width)),"X-Screen-Native-Height":String(Int(bounds.height))]
      upload = request("app-screen/frame",body:bytes,headers:headers,limit:4096) { code,body in
        guard self.live, self.valid() else { self.releaseSlot(); return }
        if code == 401 || code == 403 || code == 410 { self.end("共享授权已失效"); self.releaseSlot(); return }
        if (code == 200 || code == 202), let body = body, let next = body["barrier"] as? String, next.range(of:"^[0-9a-f]{32}$",options:.regularExpression) != nil {
          self.barrier = next
          // A response/action invalidates every sample captured before that response.
          self.afterResponse = CMClockGetTime(CMClockGetHostTimeClock())
          self.lock.lock(); self.pending = nil; self.lock.unlock()
          self.fastUntil = next.contains(where:{$0 != "0"}) ? ProcessInfo.processInfo.systemUptime + 2.5 : 0
          self.publish("画面传输：共享中")
        } else { self.publish("画面上传暂不可用，正在重试") }
        self.upload = nil; self.releaseSlot()
      }
    }
  }
  private func releaseSlot() {
    lock.lock(); let hasPending = pending != nil; if !hasPending { scheduled = false }; lock.unlock()
    if hasPending { worker.async { self.drain() } }
  }
  private func valid() -> Bool {
    guard live, let grant = CaptureContract.validGrant(), grant["id"] as? String == grantID, grant["ticket"] as? String == ticket else { if live { end("共享已停止或授权过期") }; return false }
    return true
  }
  private func tick() {
    guard valid() else { return }; publish("共享中"); pollPreparationWindow()
    let now = ProcessInfo.processInfo.systemUptime
    guard !polling, now - lastPoll >= 2 else { return }; lastPoll = now; polling = true
    statusRequest = request("app-screen/status",body:Data(),headers:[:],limit:16384) { code,body in
      self.polling = false; self.statusRequest = nil
      guard self.valid() else { return }
      if code == 401 || code == 403 || code == 410 { self.end("共享授权已失效"); return }
      if let body = body, let bytes = try? JSONSerialization.data(withJSONObject:body), bytes.count <= 7000 { self.taskStatus = String(data:bytes,encoding:.utf8) ?? "" }
      else { self.taskStatus = "" }
    }
  }
  private func pollPreparationWindow() {
    guard valid(), !windowInFlight else { return }; windowInFlight = true
    let requestedAt = ProcessInfo.processInfo.systemUptime
    let body = try! JSONSerialization.data(withJSONObject:["operation":"poll"])
    windowRequest = request("app-relay/usb-window",body:body,headers:["Content-Type":"application/json"],limit:4096,timeout:1.5) { code,response in
      self.windowRequest = nil
      guard self.valid() else { self.windowInFlight = false; return }
      guard code == 200, let response = response else { self.windowInFlight = false; return }
      let now = ProcessInfo.processInfo.systemUptime
      guard let ready = self.preparationFence.prepare(response,requestedAt:requestedAt,now:now) else { self.windowInFlight = false; return }
      // Establish the capture fence before allowing the server's existing mode gate to proceed.
      // This says nothing about whether iOS has enumerated USB CDC or accepted USB HID.
      self.afterResponse = CMClockGetTime(CMClockGetHostTimeClock())
      self.lock.lock(); self.pending = nil; self.lock.unlock()
      guard self.valid(), ProcessInfo.processInfo.systemUptime < ready.deadline,
        let bytes = try? JSONSerialization.data(withJSONObject:ready.body) else { self.windowInFlight = false; return }
      let remaining = ready.deadline - ProcessInfo.processInfo.systemUptime
      self.windowRequest = self.request("app-relay/usb-window",body:bytes,headers:["Content-Type":"application/json"],limit:4096,timeout:min(1.5,remaining)) { _,_ in
        self.windowRequest = nil; self.windowInFlight = false
      }
    }
  }
  private func publish(_ message:String) {
    // An old stream finishing after a new user grant must not overwrite its state.
    if let current = CaptureContract.read("grant.json")?["id"] as? String, current != grantID { return }
    try? CaptureContract.write("status.json",["id":grantID,"active":live,"capture":message,"task":taskStatus,"updated":Date().timeIntervalSince1970])
  }
  private func request(_ path:String,body:Data,headers:[String:String],limit:Int,timeout:TimeInterval = 5,complete:@escaping(Int,[String:Any]?)->Void) -> BoundedRequest? {
    guard valid() else { return nil }
    guard let base = endpoint else { end("服务地址未配置"); return nil }
    var req = URLRequest(url:base.appendingPathComponent(path)); req.httpMethod = "POST"; req.httpBody = body; req.timeoutInterval = max(0.05,timeout)
    req.setValue("Bearer \(ticket)",forHTTPHeaderField:"Authorization"); headers.forEach { req.setValue($1,forHTTPHeaderField:$0) }
    let requestTicket = ticket
    return BoundedRequest(req,limit:limit) { code,data in self.worker.async {
      guard self.live else { return }
      if self.valid(), self.ticket == requestTicket { complete(code,data.flatMap { (try? JSONSerialization.jsonObject(with:$0)) as? [String:Any] }) }
      else { if path == "app-screen/frame" { self.upload = nil; self.releaseSlot() }; if path == "app-screen/status" { self.polling = false; self.statusRequest = nil } }
    } }
  }
  private func end(_ reason:String) {
    guard live || onStopped != nil else { return }; live = false; heartbeat?.cancel(); heartbeat = nil; upload?.cancel(); statusRequest?.cancel(); windowRequest?.cancel(); windowRequest = nil; windowInFlight = false
    lock.lock(); pending = nil; accepting = false; lock.unlock()
    if CaptureContract.read("grant.json")?["id"] as? String == grantID { CaptureContract.clearGrant() }
    if !ticket.isEmpty { CaptureContract.revoke(ticket,base:endpoint); ticket = "" }
    taskStatus = ""; publish(reason)
    let callback = onStopped; onStopped = nil
    DispatchQueue.main.async { callback?(reason) }
  }
}
