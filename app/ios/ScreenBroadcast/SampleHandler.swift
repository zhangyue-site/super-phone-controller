import ReplayKit

/// Legacy system-consented broadcast route for iOS 15–26.
final class SampleHandler: RPBroadcastSampleHandler {
  private let pipeline = CapturePipeline()
  override func broadcastStarted(withSetupInfo setupInfo: [String: NSObject]?) {
    pipeline.start(onStopped:{ [weak self] reason in
      self?.finishBroadcastWithError(NSError(domain:"ScreenBroadcast",code:1,userInfo:[NSLocalizedDescriptionKey:reason]))
    })
  }
  override func processSampleBuffer(_ sampleBuffer: CMSampleBuffer, with sampleBufferType: RPSampleBufferType) {
    guard sampleBufferType == .video else { return }
    let orientation = (CMGetAttachment(sampleBuffer,key:RPVideoSampleOrientationKey as CFString,attachmentModeOut:nil) as? NSNumber)?.uint32Value ?? 1
    pipeline.submit(sampleBuffer,orientation:orientation,capturedAt:CMSampleBufferGetPresentationTimeStamp(sampleBuffer))
  }
  override func broadcastPaused() { pipeline.stop("系统已暂停共享，请重新授权") }
  override func broadcastResumed() { pipeline.stop("共享已中断，请重新授权") }
  override func broadcastFinished() { pipeline.stop("系统已停止共享",notify:false) }
}
