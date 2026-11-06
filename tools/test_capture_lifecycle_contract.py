"""Android service lifecycle contract; no device or projection permission required."""
import unittest
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
ANDROID = "{http://schemas.android.com/apk/res/android}"
NATIVE = ROOT / "app/android/app/src/main/kotlin/org/example/phonecontroller"

class CaptureLifecycleContract(unittest.TestCase):
    def test_projection_service_survives_usb_temporary_task_removal(self):
        manifest = ElementTree.parse(ROOT / "app/android/app/src/main/AndroidManifest.xml")
        service = next(s for s in manifest.findall("./application/service")
                       if s.get(ANDROID + "name") == ".ScreenShareService")
        self.assertEqual(service.get(ANDROID + "foregroundServiceType"), "mediaProjection")
        self.assertEqual(service.get(ANDROID + "exported"), "false")
        self.assertEqual(service.get(ANDROID + "stopWithTask"), "false",
                         "USB re-enumeration removes a temporary task; it must not revoke valid projection")

    def test_explicit_physical_and_system_revocation_paths_remain(self):
        service = (NATIVE / "ScreenShareService.kt").read_text()
        usb = (NATIVE / "UsbLaunchBridge.kt").read_text()
        self.assertIn('intent?.action=="STOP"', service)
        self.assertIn('override fun onStop()', service)
        self.assertIn('endCapture();stopSelf()', service)
        self.assertIn('intent.action!=UsbManager.ACTION_USB_DEVICE_DETACHED', usb)
        self.assertIn('"physical_detach"', usb)
        self.assertIn('app.stopService(Intent(app,ScreenShareService::class.java))', usb)

    def test_task_removal_callback_only_observes(self):
        service = (NATIVE / "ScreenShareService.kt").read_text()
        callback = service.split("override fun onTaskRemoved(rootIntent: Intent?) {", 1)[1].split("override fun onDestroy()", 1)[0]
        self.assertIn('"capture_task_removed"', callback)
        self.assertIn('"task_removed"', callback)
        for revoke in ("stopSelf(", "endCapture(", "projection?.stop(", "stopService("):
            self.assertNotIn(revoke, callback)

if __name__ == "__main__":
    unittest.main()
