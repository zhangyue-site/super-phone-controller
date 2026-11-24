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

    def test_automatic_recognition_is_scoped_to_the_native_capture(self):
        service = (NATIVE / "ScreenShareService.kt").read_text()
        card = (ROOT / "app/lib/local_auto_loop.dart").read_text()
        self.assertIn("latestLoopFrame?.captureEpoch", service)
        self.assertIn("autoEpoch!=captureGeneration", service)
        self.assertIn("localRecognitionId.isNotEmpty()", service)
        self.assertIn("autoStep", card)
        self.assertIn("'autoEpoch': autoEpoch", card)

    def test_task_removal_callback_only_observes(self):
        service = (NATIVE / "ScreenShareService.kt").read_text()
        callback = service.split("override fun onTaskRemoved(rootIntent: Intent?) {", 1)[1].split("override fun onDestroy()", 1)[0]
        self.assertIn('"capture_task_removed"', callback)
        self.assertIn('"task_removed"', callback)
        for revoke in ("stopSelf(", "endCapture(", "projection?.stop(", "stopService("):
            self.assertNotIn(revoke, callback)

class WirelessDebugPrivacyContract(unittest.TestCase):
    def test_manual_settings_entry_and_legacy_cache_cleanup(self):
        manifest = ElementTree.parse(ROOT / "app/android/app/src/main/AndroidManifest.xml")
        receiver = next(r for r in manifest.findall("./application/receiver")
                        if r.get(ANDROID + "name") == ".LegacyDebugCacheCleanup")
        self.assertEqual(receiver.get(ANDROID + "exported"), "false")
        action = receiver.find("./intent-filter/action")
        self.assertEqual(action.get(ANDROID + "name"), "android.intent.action.MY_PACKAGE_REPLACED")
        cleanup = (NATIVE / "LegacyDebugCacheCleanup.kt").read_text()
        self.assertIn('context.deleteSharedPreferences("adb-guide")', cleanup)
        self.assertNotIn("getSharedPreferences", cleanup)
        activity = (NATIVE / "MainActivity.kt").read_text()
        self.assertIn("LegacyDebugCacheCleanup.clear(this)", activity)
        entry = activity.split('"openDeveloperSettings" -> {', 1)[1].split('"diagnosticEvent"', 1)[0]
        self.assertIn("ScreenShareService.active", entry)
        self.assertIn("Settings.ACTION_APPLICATION_DEVELOPMENT_SETTINGS", entry)

    def test_retired_debug_automation_is_absent_from_app_and_backup_sources(self):
        paths = [*NATIVE.glob("*.kt*"), *(ROOT / "app/lib").glob("*.dart*")]
        forbidden = ('"adb_enabled"', '"pair_code"', '"pair_port"',
                     '"adbGuideArm"', '"enabled_accessibility_services"', '"accessibility_enabled"')
        for path in paths:
            source = path.read_text()
            for line in source.splitlines():
                if '"adb_wifi_enabled"' in line:
                    self.assertIn("Settings.Global.getInt(", line, path.name)
            for marker in forbidden:
                self.assertNotIn(marker, source, f"{path.name}: retired debug automation")


if __name__ == "__main__":
    unittest.main()
