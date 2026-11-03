import Foundation
import Security
import LocalAuthentication

/// Only three small capture-state records are shared. Images/audio and control tickets never enter storage.
enum CaptureContract {
  private static let recordNames: Set<String> = ["grant.json", "status.json", "endpoint.json"]
  private static let recordLimit = 16384
  static var group: String { Bundle.main.object(forInfoDictionaryKey: "CaptureKeychainGroup") as? String ?? "" }
  private static var configuredGroup: String? {
    let value = group
    // Fail closed on an unsigned/unexpanded build or a missing project-specific group.
    guard value.range(of:"^[A-Za-z0-9]{10}\\.[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*\\.capture$",options:.regularExpression) != nil else { return nil }
    return value
  }
  private static func query(_ name: String) -> [String: Any]? {
    guard recordNames.contains(name), let group = configuredGroup else { return nil }
    let context = LAContext(); context.interactionNotAllowed = true
    return [
      kSecClass as String: kSecClassGenericPassword,
      kSecAttrService as String: "\(group).ephemeral-capture.v1",
      kSecAttrAccount as String: name,
      kSecAttrAccessGroup as String: group,
      kSecAttrSynchronizable as String: false,
      kSecUseAuthenticationContext as String: context
    ]
  }
  /// Read preflight only; the first write still verifies the actual signed entitlement.
  static var storageAvailable: Bool {
    guard var request = query("endpoint.json") else { return false }
    request[kSecMatchLimit as String] = kSecMatchLimitOne
    let status = SecItemCopyMatching(request as CFDictionary, nil)
    return status == errSecSuccess || status == errSecItemNotFound
  }
  static var base: URL? {
    guard let value = (read("endpoint.json")?["baseUrl"] as? String) ?? (Bundle.main.object(forInfoDictionaryKey: "ControllerBaseURL") as? String),
          let url = URL(string: value), url.scheme == "https", url.host != nil, url.user == nil, url.password == nil, url.query == nil, url.fragment == nil else { return nil }
    return url
  }
  static func read(_ name: String) -> [String: Any]? {
    guard var request = query(name) else { return nil }
    request[kSecMatchLimit as String] = kSecMatchLimitOne
    request[kSecReturnData as String] = true
    var result: CFTypeRef?
    guard SecItemCopyMatching(request as CFDictionary, &result) == errSecSuccess,
      let data = result as? Data, data.count <= recordLimit else { return nil }
    return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
  }
  static func write(_ name: String, _ body: [String: Any]) throws {
    guard let request = query(name) else { throw storageError(errSecParam) }
    let data = try JSONSerialization.data(withJSONObject: body)
    guard data.count <= recordLimit else { throw storageError(errSecDataTooLarge) }
    let attributes: [String: Any] = [
      kSecValueData as String: data,
      kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
    ]
    // Atomic replacement of one record, without a delete/add gap for the extension.
    var status = SecItemUpdate(request as CFDictionary, attributes as CFDictionary)
    if status == errSecItemNotFound {
      var item = request
      // Authentication-UI control is query-only; access group and synchronization remain explicit.
      item.removeValue(forKey:kSecUseAuthenticationContext as String)
      attributes.forEach { item[$0.key] = $0.value }
      status = SecItemAdd(item as CFDictionary, nil)
      if status == errSecDuplicateItem { status = SecItemUpdate(request as CFDictionary, attributes as CFDictionary) }
    }
    guard status == errSecSuccess else { throw storageError(status) }
  }
  // BEGIN updateExistingGrant
  /// A renewal must never recreate a capability removed by STOP or another capture process.
  static func updateExistingGrant(_ body: [String: Any], expectedID: String) throws {
    guard !expectedID.isEmpty, body["id"] as? String == expectedID,
      validGrant()?["id"] as? String == expectedID,
      let request = query("grant.json") else { throw storageError(errSecItemNotFound) }
    let data = try JSONSerialization.data(withJSONObject: body)
    guard data.count <= recordLimit else { throw storageError(errSecDataTooLarge) }
    let attributes: [String: Any] = [
      kSecValueData as String: data,
      kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
    ]
    // Delete and update serialize inside Keychain. Missing means revoked, never insert.
    let status = SecItemUpdate(request as CFDictionary, attributes as CFDictionary)
    guard status == errSecSuccess else { throw storageError(status) }
  }
  // END updateExistingGrant
  static func clearGrant() {
    // Remove task presentation along with the capability; keep only the non-secret endpoint setting.
    for name in ["grant.json", "status.json"] {
      if var request = query(name) {
        request.removeValue(forKey:kSecUseAuthenticationContext as String)
        SecItemDelete(request as CFDictionary)
      }
    }
  }
  private static func storageError(_ code: OSStatus) -> NSError {
    NSError(domain:"CaptureStorage",code:Int(code),userInfo:[NSLocalizedDescriptionKey:"共享安全存储不可用，请检查应用签名和共享钥匙串配置"])
  }
  static func validGrant() -> [String: Any]? {
    guard let grant = read("grant.json"), let ticket = grant["ticket"] as? String,
      ticket.range(of: "^[A-Za-z0-9_-]{43}$", options: .regularExpression) != nil,
      let until = grant["until"] as? Double, until > Date().timeIntervalSince1970,
      let bootUntil = grant["uptimeUntil"] as? Double, bootUntil > ProcessInfo.processInfo.systemUptime,
      let issued = grant["issuedUptime"] as? Double, issued <= ProcessInfo.processInfo.systemUptime else { return nil }
    return grant
  }
  static func revoke(_ ticket: String, base: URL? = nil) {
    guard let base = base ?? CaptureContract.base else { return }
    var request = URLRequest(url: base.appendingPathComponent("app-screen/stop"))
    request.httpMethod = "POST"; request.timeoutInterval = 3
    request.setValue("Bearer \(ticket)", forHTTPHeaderField: "Authorization")
    _ = BoundedRequest(request, limit: 4096) { _, _ in }
  }
}
