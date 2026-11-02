import ReplayKit
import CoreImage
import ImageIO

/// ReplayKit callback returns promptly; worker holds at most one latest sample and one upload.
final class SampleHandler: RPBroadcastSampleHandler {
  private let worker = DispatchQueue(label:"screen.broadcast")
  private let lock = NSLock()
  private var pending: CMSampleBuffer?
  private var scheduled = false
  private var grantID = "", ticket = "", barrier = ""
  private var sequence = 0
  private var afterResponse = CMTime.zero
  private var geometry: (Int,Int,UInt32)?
  private var lastFrame = 0.0, fastUntil = 0.0, lastPoll = 0.0
  private var live = false, polling = false
  private var heartbeat: DispatchSourceTimer?
  private var upload: BoundedRequest?, statusRequest: BoundedRequest?
  private var taskStatus = ""
  private let context = CIContext(options:[.cacheIntermediates:false])
  override func broadcastStarted(withSetupInfo setupInfo: [String : NSObject]?) {
    worker.async {
      guard let grant = CaptureContract.validGrant(), let id = grant["id"] as? String, let ticket = grant["ticket"] as? String else { self.end("授权已过期，请重新共享"); return }
      self.grantID = id; self.ticket = ticket; self.live = true
      self.publish("共享中，等待任务")
      let timer = DispatchSource.makeTimerSource(queue:self.worker); self.heartbeat = timer
      timer.schedule(deadline:.now(),repeating:1); timer.setEventHandler { [weak self] in self?.tick() }; timer.resume()
    }
  }
  override func processSampleBuffer(_ sampleBuffer: CMSampleBuffer, with sampleBufferType: RPSampleBufferType) {
    guard sampleBufferType == .video, CMSampleBufferDataIsReady(sampleBuffer) else { return }
    lock.lock(); pending = sampleBuffer
    if scheduled { lock.unlock(); return }; scheduled = true; lock.unlock()
    worker.async { self.drain() }
  }
  private func drain() {
    lock.lock(); let sample = pending; pending = nil; lock.unlock()
    guard live, valid(), let sample = sample else { releaseSlot(); return }
    let now = ProcessInfo.processInfo.systemUptime
    guard now - lastFrame >= (now < fastUntil ? 0.1 : 0.8), CMTimeCompare(CMSampleBufferGetPresentationTimeStamp(sample),afterResponse) > 0,
      let buffer = CMSampleBufferGetImageBuffer(sample) else { releaseSlot(); return }
    let orientation = (CMGetAttachment(sample,key:RPVideoSampleOrientationKey,attachmentModeOut:nil) as? NSNumber)?.uint32Value ?? 1
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
      let headers = ["Content-Type":"image/jpeg","X-Screen-Sequence":String(sequence),"X-Screen-Barrier":barrier,"X-Screen-Native-Width":String(Int(bounds.width)),"X-Screen-Native-Height":String(Int(bounds.height))]
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
    guard live, let grant = CaptureContract.validGrant(), grant["id"] as? String == grantID, let current = grant["ticket"] as? String else { if live { end("共享已停止或授权过期") }; return false }
    if current != ticket {
      // Same authorized broadcast, freshly BLE-proved capability. Old callbacks cannot update new state.
      upload?.cancel(); statusRequest?.cancel(); ticket = current; sequence = 0; barrier = ""; taskStatus = ""
      afterResponse = CMClockGetTime(CMClockGetHostTimeClock()); fastUntil = 0
      lock.lock(); pending = nil; lock.unlock()
    }
    return true
  }
  private func tick() {
    guard valid() else { return }; publish("共享中")
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
  private func publish(_ message:String) { try? CaptureContract.write("status.json",["id":grantID,"active":live,"capture":message,"task":taskStatus,"updated":Date().timeIntervalSince1970]) }
  private func request(_ path:String,body:Data,headers:[String:String],limit:Int,complete:@escaping(Int,[String:Any]?)->Void) -> BoundedRequest? {
    guard let base = CaptureContract.base else { end("服务地址未配置"); return nil }
    var req = URLRequest(url:base.appendingPathComponent(path)); req.httpMethod = "POST"; req.httpBody = body; req.timeoutInterval = 5
    req.setValue("Bearer \(ticket)",forHTTPHeaderField:"Authorization"); headers.forEach { req.setValue($1,forHTTPHeaderField:$0) }
    let requestTicket = ticket
    return BoundedRequest(req,limit:limit) { code,data in self.worker.async {
      guard self.live else { return }
      if self.valid(), self.ticket == requestTicket { complete(code,data.flatMap { (try? JSONSerialization.jsonObject(with:$0)) as? [String:Any] }) }
      else { if path == "app-screen/frame" { self.upload = nil; self.releaseSlot() }; if path == "app-screen/status" { self.polling = false; self.statusRequest = nil } }
    } }
  }
  private func end(_ reason:String,finish:Bool = true) {
    let wasLive = live; live = false; heartbeat?.cancel(); heartbeat = nil; upload?.cancel(); statusRequest?.cancel()
    lock.lock(); pending = nil; lock.unlock()
    if CaptureContract.read("grant.json")?["id"] as? String == grantID { CaptureContract.clearGrant() }
    if !ticket.isEmpty { CaptureContract.revoke(ticket); ticket = "" }
    taskStatus = ""; publish(reason)
    if finish && (wasLive || grantID.isEmpty) { finishBroadcastWithError(NSError(domain:"ScreenBroadcast",code:1,userInfo:[NSLocalizedDescriptionKey:reason])) }
  }
  override func broadcastPaused() { worker.async { self.end("系统已暂停共享，请重新授权") } }
  override func broadcastResumed() { worker.async { self.end("共享已中断，请重新授权") } }
  override func broadcastFinished() { worker.async { self.end("系统已停止共享",finish:false) } }
}
