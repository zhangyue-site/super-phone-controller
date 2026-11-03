import Flutter
import UIKit
import ReplayKit

final class NativeBridge {
  private weak var controller: FlutterViewController?
  private var channels: [FlutterMethodChannel] = []
  private var consent: CaptureConsentController?
  private var modernCapture: ScreenCaptureSession?
  init(messenger: FlutterBinaryMessenger) {
    for name in ["app", "screen", "usb"] {
      let channel = FlutterMethodChannel(name: "pcflash/\(name)", binaryMessenger: messenger)
      channel.setMethodCallHandler { [weak self] call, reply in self?.handle(name, call, reply) }
      channels.append(channel)
    }
    // Never resume a capability from a previous host process.
    if let ticket = CaptureContract.read("grant.json")?["ticket"] as? String { CaptureContract.clearGrant(); CaptureContract.revoke(ticket) }
  }
  func connectController(_ controller: FlutterViewController) { self.controller = controller }
  func disconnectController(_ controller: FlutterViewController) {
    guard self.controller === controller else { return }
    // Only actual scene disconnection revokes consent. Cross-app capture backgrounds normally.
    let ticket = CaptureContract.read("grant.json")?["ticket"] as? String
    CaptureContract.clearGrant()
    if let ticket = ticket { CaptureContract.revoke(ticket) }
    consent?.cancel(); modernCapture?.cancel()
    self.controller = nil
  }
  private func fail(_ reply: FlutterResult, _ code: String, _ message: String) { reply(FlutterError(code: code, message: message, details: nil)) }
  private func handle(_ channel: String, _ call: FlutterMethodCall, _ reply: @escaping FlutterResult) {
    let args = call.arguments as? [String: Any] ?? [:]
    if channel == "usb" {
      if call.method == "snapshot" { reply(nil); return }
      fail(reply, "usb_unsupported", "iOS 不提供此 USB CDC 证明通道；请使用真实蓝牙身份授权，USB HID 需实机验收"); return
    }
    if channel == "app" {
      switch call.method {
      case "appearance": reply(UserDefaults.standard.string(forKey: "appearance") ?? "system")
      case "setAppearance":
        guard let mode = args["mode"] as? String, ["system", "light", "dark"].contains(mode) else { fail(reply,"invalid_mode","主题设置无效"); return }
        UserDefaults.standard.set(mode, forKey: "appearance"); reply(nil)
      case "info": reply(["versionName": Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "", "versionCode": Int(Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "") ?? 0])
      case "diagnostics": reply("[]")
      case "diagnosticEvent": reply(nil) // Never persist arbitrary diagnostic payloads or secrets.
      case "openSettings": UIApplication.shared.open(URL(string: UIApplication.openSettingsURLString)!); reply(nil)
      case "openDownload":
        guard let value = Bundle.main.object(forInfoDictionaryKey: "DownloadURL") as? String, let url = URL(string: value), url.scheme == "https", url.host != nil else { fail(reply,"not_configured","更新入口尚未配置"); return }
        UIApplication.shared.open(url, options: [:]) { ok in ok ? reply(nil) : self.fail(reply,"browser_unavailable","无法打开更新入口") }
      default: reply(FlutterMethodNotImplemented)
      }; return
    }
    switch call.method {
    case "status":
      let status = CaptureContract.read("status.json") ?? [:]
      let fresh = (status["updated"] as? Double ?? 0) > Date().timeIntervalSince1970 - 6
      let grant = CaptureContract.validGrant()
      let active = grant != nil && status["id"] as? String == grant?["id"] as? String && fresh && status["active"] as? Bool == true
      let body: [String: Any] = ["active": active, "capture": active ? (status["capture"] as? String ?? "共享中") : "未共享", "task": active ? (status["task"] as? String ?? "") : ""]
      reply(String(data: try! JSONSerialization.data(withJSONObject: body), encoding: .utf8))
    case "start":
      guard let presenter = controller, presenter.viewIfLoaded?.window != nil,
        presenter.presentedViewController == nil else { fail(reply,"scene_unavailable","界面尚未就绪，请返回应用后重新共享"); return }
      guard consent == nil, modernCapture == nil else { fail(reply,"busy","共享正在准备或运行"); return }
      guard args["usbSession"] == nil else { fail(reply,"usb_unsupported","iOS USB CDC 会话不可用，请通过蓝牙授权共享"); return }
      if let value = args["baseUrl"] as? String {
        guard let url = URL(string:value), url.scheme == "https", url.host != nil, url.user == nil, url.password == nil, url.query == nil, url.fragment == nil else { fail(reply,"invalid_endpoint","共享服务地址必须为 HTTPS"); return }
        guard CaptureContract.validGrant() == nil else { fail(reply,"busy","共享正在运行"); return }
        do { try CaptureContract.write("endpoint.json",["baseUrl":value]) } catch { fail(reply,"storage_failed","无法保存共享服务地址"); return }
      }
      guard CaptureContract.base != nil, CaptureContract.storageAvailable else { fail(reply,"not_configured","共享服务或专用共享钥匙串尚未配置"); return }
      guard consent == nil, CaptureContract.validGrant() == nil, let ticket = args["ticket"] as? String, ticket.range(of: "^[A-Za-z0-9_-]{43}$", options: .regularExpression) != nil else { fail(reply,"busy","共享正在准备或凭证无效"); return }
      #if !canImport(ScreenCaptureKit)
      if #available(iOS 27.0, *) { fail(reply,"capture_sdk_unavailable","请安装使用 iOS 27 SDK 构建的应用版本以共享屏幕"); return }
      #endif
      let now = Date().timeIntervalSince1970, uptime = ProcessInfo.processInfo.systemUptime
      do { try CaptureContract.write("grant.json", ["ticket": ticket,"id": UUID().uuidString,"until": now + 270,"uptimeUntil": uptime + 270,"issuedUptime": uptime]) }
      catch { fail(reply,"storage_failed","无法准备受限共享授权"); return }
      #if canImport(ScreenCaptureKit)
      if #available(iOS 27.0, *) {
        let session = SCKCaptureSession(); modernCapture = session
        session.onEnded = { [weak self, weak session] in
          if self?.modernCapture === session { self?.modernCapture = nil }
        }
        session.start { [weak self] message in
          if let message = message { self?.fail(reply,"cancelled",message) } else { reply(nil) }
        }
        return
      }
      #endif
      let view = CaptureConsentController()
      view.extensionID = Bundle.main.object(forInfoDictionaryKey: "BroadcastExtensionID") as? String
      view.finished = { [weak self] started in
        self?.consent = nil
        if started { reply(nil) } else { CaptureContract.clearGrant(); CaptureContract.revoke(ticket); self?.fail(reply,"cancelled","未启动屏幕共享") }
      }
      consent = view; presenter.present(view, animated: true)
    case "stop":
      let ticket = CaptureContract.read("grant.json")?["ticket"] as? String
      CaptureContract.clearGrant(); if let ticket = ticket { CaptureContract.revoke(ticket) }
      consent?.cancel(); modernCapture?.cancel(); reply(nil)
    case "renewCapture":
      guard let grant = CaptureContract.validGrant(), let ticket = grant["ticket"] as? String, let grantID = grant["id"] as? String,
        let control = args["controlTicket"] as? String, control.range(of:"^[A-Za-z0-9_-]{43}$", options:.regularExpression) != nil,
        let base = CaptureContract.base else { fail(reply,"capture_session_invalid","共享授权已失效"); return }
      let state = CaptureContract.read("status.json") ?? [:]
      guard state["id"] as? String == grant["id"] as? String, state["active"] as? Bool == true,
        (state["updated"] as? Double ?? 0) > Date().timeIntervalSince1970 - 6 else { fail(reply,"capture_session_invalid","系统广播已结束"); return }
      var request = URLRequest(url: base.appendingPathComponent("app-control/screen-renew")); request.httpMethod = "POST"; request.timeoutInterval = 3
      request.setValue("Bearer \(control)", forHTTPHeaderField:"Authorization"); request.setValue("application/json", forHTTPHeaderField:"Content-Type")
      request.httpBody = try? JSONSerialization.data(withJSONObject: ["ticket":ticket])
      _ = BoundedRequest(request,limit:4096) { code,data in DispatchQueue.main.async {
        guard code == 200, let data = data,
          let body = (try? JSONSerialization.jsonObject(with:data)) as? [String:Any], body["scope"] as? String == "screen-frames", body["expiresIn"] as? Int == 300,
          CaptureContract.validGrant()?["id"] as? String == grantID else { self.fail(reply,"capture_renew_failed","共享续期失败"); return }
        var renewed = grant; renewed["until"] = Date().timeIntervalSince1970 + 270; renewed["uptimeUntil"] = ProcessInfo.processInfo.systemUptime + 270
        do { try CaptureContract.updateExistingGrant(renewed, expectedID: grantID); reply(nil) } catch { self.fail(reply,"storage_failed","续期未保存") }
      }}
    case "captureSession", "replaceUsbCapture", "renewUsbCapture", "usbWindow": fail(reply,"usb_unsupported","iOS USB CDC 共享恢复不可用")
    default: reply(FlutterMethodNotImplemented)
    }
  }
}

final class CaptureConsentController: UIViewController {
  var extensionID: String?
  var finished: ((Bool) -> Void)?
  private var timer: Timer?
  private let deadline = Date().addingTimeInterval(60)
  override func viewDidLoad() {
    super.viewDidLoad(); view.backgroundColor = .systemBackground
    isModalInPresentation = true
    let label = UILabel(); label.text = "请点系统广播按钮，然后确认开始直播。仅共享画面；操作由控制板 HID 完成。"; label.numberOfLines = 0; label.textAlignment = .center
    let picker = RPSystemBroadcastPickerView(frame: CGRect(x:0,y:0,width:64,height:64)); picker.preferredExtension = extensionID; picker.showsMicrophoneButton = false
    picker.accessibilityLabel = "系统屏幕广播授权"
    let cancel = UIButton(type:.system); cancel.setTitle("取消共享",for:.normal); cancel.addTarget(self,action:#selector(cancelTapped),for:.touchUpInside)
    let stack = UIStackView(arrangedSubviews:[label,picker,cancel]); stack.axis = .vertical; stack.alignment = .center; stack.spacing = 24; stack.translatesAutoresizingMaskIntoConstraints = false
    view.addSubview(stack); NSLayoutConstraint.activate([stack.centerYAnchor.constraint(equalTo:view.centerYAnchor),stack.leadingAnchor.constraint(equalTo:view.safeAreaLayoutGuide.leadingAnchor,constant:24),stack.trailingAnchor.constraint(equalTo:view.safeAreaLayoutGuide.trailingAnchor,constant:-24),label.widthAnchor.constraint(equalTo:stack.widthAnchor),picker.heightAnchor.constraint(equalToConstant:64),picker.widthAnchor.constraint(equalToConstant:64)])
    timer = Timer.scheduledTimer(withTimeInterval:0.5,repeats:true) { [weak self] _ in self?.check() }
  }
  private func check() {
    if let grant = CaptureContract.validGrant(), let status = CaptureContract.read("status.json"), status["id"] as? String == grant["id"] as? String, status["active"] as? Bool == true { complete(true) }
    else if Date() > deadline || CaptureContract.validGrant() == nil { complete(false) }
  }
  @objc private func cancelTapped() { cancel() }
  func cancel() { complete(false) }
  private func complete(_ success: Bool) { guard let callback = finished else { return }; finished = nil; timer?.invalidate(); timer = nil; dismiss(animated:true); callback(success) }
  deinit { timer?.invalidate() }
}
