import Foundation

/// Version-independent lifecycle owned by NativeBridge; no fabricated USB session.
protocol ScreenCaptureSession: AnyObject {
  var onEnded: (() -> Void)? { get set }
  func start(completion: @escaping (String?) -> Void)
  func cancel()
}
