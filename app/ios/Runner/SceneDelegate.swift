import Flutter
import UIKit

/// Scene ownership is separate from engine lifetime. Backgrounding is not consent revocation.
class SceneDelegate: FlutterSceneDelegate {
  private weak var flutterController: FlutterViewController?

  override func scene(_ scene: UIScene, willConnectTo session: UISceneSession, options connectionOptions: UIScene.ConnectionOptions) {
    super.scene(scene, willConnectTo: session, options: connectionOptions)
    guard let controller = window?.rootViewController as? FlutterViewController else { return }
    flutterController = controller
    (UIApplication.shared.delegate as? AppDelegate)?.connectController(controller)
  }

  override func sceneDidDisconnect(_ scene: UIScene) {
    if let controller = flutterController {
      (UIApplication.shared.delegate as? AppDelegate)?.disconnectController(controller)
    }
    flutterController = nil
    super.sceneDidDisconnect(scene)
  }
}
