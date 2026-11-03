#if canImport(ScreenCaptureKit)
import UIKit
import ScreenCaptureKit
import CoreMedia

/// iOS 27 full-display capture. Every lifecycle mutation is serialized on the main queue.
@available(iOS 27.0, *)
final class SCKCaptureSession: NSObject, ScreenCaptureSession, SCContentSharingPickerObserver, SCStreamOutput, SCStreamDelegate {
  var onEnded: (() -> Void)?
  private let pipeline = CapturePipeline()
  private let picker = SCContentSharingPicker.shared
  private var stream: SCStream?
  private var completion: ((String?) -> Void)?
  private var timeout: Timer?
  private var ended = false
  private var grantID = ""
  private var ticket = ""
  private var endpoint: URL?
  private var hasSelection = false

  func start(completion: @escaping (String?) -> Void) {
    dispatchPrecondition(condition:.onQueue(.main))
    self.completion = completion
    guard let grant = CaptureContract.validGrant(), let id = grant["id"] as? String, let capability = grant["ticket"] as? String else { end("共享授权已过期"); return }
    grantID = id; ticket = capability; endpoint = CaptureContract.base
    guard picker.isAvailable else { end("系统不允许屏幕共享，请检查系统限制后重试"); return }
    var config = SCContentSharingPickerConfiguration()
    config.showsMicrophoneControl = false; config.showsCameraControl = false
    picker.defaultConfiguration = config
    picker.add(self); picker.isActive = true
    timeout = Timer.scheduledTimer(withTimeInterval:60,repeats:false) { [weak self] _ in self?.end("未完成屏幕共享授权，请重试") }
    // Full-display selection preserves the HID normalized-coordinate contract.
    // allowedPickerModes and maximumStreamCount are unavailable on iOS.
    picker.present(using:.display)
  }

  func cancel() { end("已取消屏幕共享") }

  func contentSharingPicker(_ picker: SCContentSharingPicker, didUpdateWith filter: SCContentFilter, for stream: SCStream?) {
    DispatchQueue.main.async { [weak self] in self?.applySelection(filter) }
  }
  private func applySelection(_ filter: SCContentFilter) {
    guard !ended, CaptureContract.validGrant()?["id"] as? String == grantID else { end("共享请求已失效"); return }
    guard !hasSelection, stream == nil else { end("共享范围已改变，请重新授权"); return }; hasSelection = true
    guard filter.style == .display else { end("请选择整个屏幕，以便核验控制板操作"); return }
    let rect = filter.contentRect, scale = CGFloat(filter.pointPixelScale)
    guard rect.width.isFinite, rect.height.isFinite, scale.isFinite, rect.width > 0, rect.height > 0, scale > 0,
      rect.width * scale <= 16384, rect.height * scale <= 16384 else { end("系统返回的屏幕尺寸无效"); return }
    let config = SCStreamConfiguration()
    // Keep the native full display; shared pipeline performs bounded JPEG scaling.
    config.width = max(1,Int((rect.width * scale).rounded()))
    config.height = max(1,Int((rect.height * scale).rounded()))
    config.capturesAudio = false
    // iOS does not support queueDepth/minimumFrameInterval/pixelFormat overrides.
    let newStream = SCStream(filter:filter,configuration:config,delegate:self)
    do { try newStream.addStreamOutput(self,type:.screen,sampleHandlerQueue:.main) }
    catch { end("无法连接系统画面流，请重新授权"); return }
    self.stream = newStream
    newStream.startCapture { [weak self] error in DispatchQueue.main.async {
      guard let self = self, !self.ended else { newStream.stopCapture(completionHandler:nil); return }
      guard error == nil, newStream.isCapturing, CaptureContract.validGrant()?["id"] as? String == self.grantID else { self.end("系统屏幕共享未启动，请重试"); return }
      self.pipeline.start(onStarted:{ [weak self] in
        guard let self = self, !self.ended else { return }
        guard CaptureContract.validGrant()?["id"] as? String == self.grantID, newStream.isCapturing else { self.end("共享请求已失效"); return }
        self.timeout?.invalidate(); self.timeout = nil
        let callback = self.completion; self.completion = nil; callback?(nil)
      },onStopped:{ [weak self] reason in self?.end(reason) })
    }}
  }

  func contentSharingPicker(_ picker: SCContentSharingPicker, didCancelFor stream: SCStream?) {
    DispatchQueue.main.async { [weak self] in self?.end("未同意屏幕共享") }
  }
  func contentSharingPickerStartDidFailWithError(_ error: Error) {
    DispatchQueue.main.async { [weak self] in self?.end("无法显示系统共享授权，请重试") }
  }
  func stream(_ stream: SCStream, didStopWithError error: Error) {
    DispatchQueue.main.async { [weak self] in self?.end("系统已停止屏幕共享") }
  }
  func streamDidBecomeInactive(_ stream: SCStream) {
    DispatchQueue.main.async { [weak self] in self?.end("共享内容已不可用，请重新授权") }
  }
  func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
    dispatchPrecondition(condition:.onQueue(.main))
    guard !ended, self.stream === stream, type == .screen,
      CMSampleBufferDataIsReady(sampleBuffer), let clock = stream.synchronizationClock,
      let attachments = CMSampleBufferGetSampleAttachmentsArray(sampleBuffer,createIfNecessary:false) as? [[SCStreamFrameInfo:Any]],
      let frame = attachments.first, let rawStatus = frame[.status] as? Int, let status = SCFrameStatus(rawValue:rawStatus) else { return }
    if status == .blank || status == .suspended || status == .stopped { end("系统共享画面已暂停，请重新授权"); return }
    // Idle buffers do not establish a new post-action screen; never replay their pixels.
    guard status == .complete, CMSampleBufferGetImageBuffer(sampleBuffer) != nil else { return }
    let orientation = (frame[.videoOrientation] as? NSNumber)?.uint32Value ?? 1
    let capturedAt = CMSyncConvertTime(CMSampleBufferGetPresentationTimeStamp(sampleBuffer),from:clock,to:CMClockGetHostTimeClock())
    pipeline.submit(sampleBuffer,orientation:orientation,capturedAt:capturedAt)
  }

  private func end(_ reason: String) {
    dispatchPrecondition(condition:.onQueue(.main))
    guard !ended else { return }; ended = true
    timeout?.invalidate(); timeout = nil
    picker.remove(self); picker.isActive = false
    if CaptureContract.read("grant.json")?["id"] as? String == grantID { CaptureContract.clearGrant() }
    if !ticket.isEmpty { CaptureContract.revoke(ticket,base:endpoint); ticket = "" }
    let old = stream; stream = nil
    old?.stopCapture(completionHandler:nil)
    pipeline.stop(reason)
    let callback = completion; completion = nil; callback?(reason)
    let didEnd = onEnded; onEnded = nil; didEnd?()
  }
  deinit { timeout?.invalidate() }
}
#endif
