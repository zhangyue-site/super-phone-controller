import Flutter
import UIKit

@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  private var nativeBridge: NativeBridge?
  private weak var sceneController: FlutterViewController?

  override func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)
    nativeBridge = NativeBridge(messenger: engineBridge.applicationRegistrar.messenger())
    if let controller = sceneController { nativeBridge?.connectController(controller) }
  }

  func connectController(_ controller: FlutterViewController) {
    sceneController = controller
    nativeBridge?.connectController(controller)
  }

  func disconnectController(_ controller: FlutterViewController) {
    guard sceneController === controller else { return }
    nativeBridge?.disconnectController(controller)
    sceneController = nil
  }
}
