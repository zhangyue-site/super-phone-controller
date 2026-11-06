import Foundation
import CoreFoundation

/// Capture-readiness acknowledgement only. It never attests USB presence or HID enumeration.
struct CapturePreparationFence {
  struct Ready {
    let nonce: String
    let mode: String
    let generation: Int
    let deadline: TimeInterval
    var body: [String: Any] { ["operation":"ready","nonce":nonce,"mode":mode,"generation":generation] }
  }
  private var lastGeneration = 0
  private var usedNonces = Set<String>()
  mutating func prepare(_ response: [String: Any], requestedAt: TimeInterval, now: TimeInterval) -> Ready? {
    guard response["state"] as? String == "prepare",
      Set(response.keys) == Set(["state","nonce","mode","generation","expiresInMs"]),
      let nonce = response["nonce"] as? String, nonce.range(of:"^[0-9a-f]{32}$",options:.regularExpression) != nil,
      !usedNonces.contains(nonce), usedNonces.count < 1024,
      let mode = response["mode"] as? String, ["hid","normal"].contains(mode),
      let generation = integer(response["generation"]), generation > lastGeneration,
      let ttl = integer(response["expiresInMs"]), (1...5000).contains(ttl),
      requestedAt.isFinite, now.isFinite, now >= requestedAt else { return nil }
    // Use request start rather than response arrival: a slow response cannot renew its lease.
    let deadline = requestedAt + Double(ttl) / 1000
    guard now < deadline else { return nil }
    lastGeneration = generation; usedNonces.insert(nonce)
    return Ready(nonce:nonce,mode:mode,generation:generation,deadline:deadline)
  }
  private func integer(_ value: Any?) -> Int? {
    guard let number = value as? NSNumber, CFGetTypeID(number) != CFBooleanGetTypeID(),
      number.doubleValue.isFinite, number.doubleValue.rounded() == number.doubleValue,
      number.doubleValue >= 1, number.doubleValue <= 9007199254740991 else { return nil }
    return number.intValue
  }
}
