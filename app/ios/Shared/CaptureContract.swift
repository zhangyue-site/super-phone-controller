import Foundation

/// Only a short-lived server capability is shared. Screens remain memory-only.
enum CaptureContract {
  static var group: String { Bundle.main.object(forInfoDictionaryKey: "CaptureAppGroup") as? String ?? "" }
  static var base: URL? {
    guard let value = (read("endpoint.json")?["baseUrl"] as? String) ?? (Bundle.main.object(forInfoDictionaryKey: "ControllerBaseURL") as? String),
          let url = URL(string: value), url.scheme == "https", url.host != nil, url.user == nil, url.password == nil, url.query == nil, url.fragment == nil else { return nil }
    return url
  }
  static var root: URL? { FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: group) }
  static func read(_ name: String) -> [String: Any]? {
    guard let url = root?.appendingPathComponent(name), let data = try? Data(contentsOf: url), data.count <= 16384 else { return nil }
    return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
  }
  static func write(_ name: String, _ body: [String: Any]) throws {
    guard let url = root?.appendingPathComponent(name) else { throw NSError(domain: "Capture", code: 1) }
    let data = try JSONSerialization.data(withJSONObject: body)
    try data.write(to: url, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
    try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: url.path)
    var values = URLResourceValues(); values.isExcludedFromBackup = true
    var mutable = url; try mutable.setResourceValues(values)
  }
  static func clearGrant() { if let url = root?.appendingPathComponent("grant.json") { try? FileManager.default.removeItem(at: url) } }
  static func validGrant() -> [String: Any]? {
    guard let grant = read("grant.json"), let ticket = grant["ticket"] as? String,
      ticket.range(of: "^[A-Za-z0-9_-]{43}$", options: .regularExpression) != nil,
      let until = grant["until"] as? Double, until > Date().timeIntervalSince1970,
      let bootUntil = grant["uptimeUntil"] as? Double, bootUntil > ProcessInfo.processInfo.systemUptime,
      let issued = grant["issuedUptime"] as? Double, issued <= ProcessInfo.processInfo.systemUptime else { return nil }
    return grant
  }
  static func revoke(_ ticket: String) {
    guard let base = base else { return }
    var request = URLRequest(url: base.appendingPathComponent("app-screen/stop"))
    request.httpMethod = "POST"; request.timeoutInterval = 3
    request.setValue("Bearer \(ticket)", forHTTPHeaderField: "Authorization")
    _ = BoundedRequest(request, limit: 4096) { _, _ in }
  }
}
