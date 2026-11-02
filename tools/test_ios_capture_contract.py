#!/usr/bin/env python3
"""Offline bundle/extension wiring checks, not an iOS build or device test."""
import pathlib
import plistlib
import re
import unittest
import shutil
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
IOS = ROOT / 'app' / 'ios'

class IOSCaptureContract(unittest.TestCase):
    def plist(self, path):
        with (IOS / path).open('rb') as stream:
            return plistlib.load(stream)

    def test_extension_configuration_and_keychain_group_agree(self):
        host = self.plist('Runner/Info.plist')
        extension = self.plist('ScreenBroadcast/Info.plist')
        self.assertEqual(host['CaptureKeychainGroup'], extension['CaptureKeychainGroup'])
        self.assertEqual(host['CaptureKeychainGroup'], '$(AppIdentifierPrefix)$(APP_BUNDLE_ID).capture')
        self.assertEqual(host['ControllerBaseURL'], extension['ControllerBaseURL'])
        self.assertEqual(host['BroadcastExtensionID'], '$(BROADCAST_BUNDLE_ID)')
        for target in ['Runner', 'ScreenBroadcast']:
            entitlements = self.plist(f'{target}/{target}.entitlements')
            self.assertEqual(entitlements, {'keychain-access-groups': [host['CaptureKeychainGroup']]})
            self.assertNotIn('CaptureAppGroup', self.plist(f'{target}/Info.plist'))
        self.assertEqual(extension['NSExtension'], {
            'NSExtensionPointIdentifier': 'com.apple.broadcast-services-upload',
            'NSExtensionPrincipalClass': '$(PRODUCT_MODULE_NAME).SampleHandler',
            'RPBroadcastProcessMode': 'RPBroadcastProcessModeSampleBuffer',
        })

    def test_capture_storage_is_bounded_project_keychain_without_file_fallback(self):
        source = (IOS / 'Shared/CaptureContract.swift').read_text()
        self.assertIn('import Security', source)
        self.assertIn('kSecClass as String: kSecClassGenericPassword', source)
        self.assertIn('kSecAttrAccessGroup as String: group', source)
        self.assertIn('kSecAttrService as String: "\\(group).ephemeral-capture.v1"', source)
        self.assertIn('kSecAttrSynchronizable as String: false', source)
        self.assertIn('kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly', source)
        self.assertIn('context.interactionNotAllowed = true', source)
        self.assertIn('private static let recordLimit = 16384', source)
        self.assertIn('recordNames.contains(name)', source)
        self.assertIn('["grant.json", "status.json", "endpoint.json"]', source)
        self.assertEqual(source.count('data.count <= recordLimit'), 2)
        self.assertIn('SecItemUpdate(', source)
        self.assertIn('SecItemAdd(', source)
        self.assertIn('SecItemDelete(', source)
        self.assertNotRegex(source, r'FileManager|containerURL|Data\(contentsOf:|controlTicket|print\(')
        native = (IOS / 'Runner/NativeBridge.swift').read_text()
        self.assertIn('CaptureContract.storageAvailable', native)
        self.assertNotIn('CaptureContract.root', native)

    def test_usb_snapshot_matches_nullable_dart_contract(self):
        native = (IOS / 'Runner/NativeBridge.swift').read_text()
        self.assertRegex(native, r'if call.method == "snapshot" \{ reply\(nil\); return \}')
        self.assertIn('"usb_unsupported"', native)
        dart = (ROOT / 'app/lib/usb_launch.dart').read_text()
        self.assertRegex(dart, r'value\s*==\s*null\s*\?\s*null\s*:\s*UsbAttachment.parse')

    def test_ios27_permissions_weak_framework_and_both_capture_routes(self):
        host = self.plist('Runner/Info.plist')
        self.assertTrue(host['NSScreenCaptureUsageDescription'])
        self.assertIn('screen-capture', host['UIBackgroundModes'])
        source = (IOS / 'Runner.xcodeproj/project.pbxproj').read_text()
        self.assertIn('System/Library/Frameworks/ScreenCaptureKit.framework', source)
        self.assertRegex(source, r'ATTRIBUTES = \(Weak, \)')
        native = (IOS / 'Runner/NativeBridge.swift').read_text()
        self.assertIn('SCKCaptureSession()', native)
        self.assertIn('CaptureConsentController()', native)
        self.assertIn('modernCapture?.cancel()', native)
        legacy = (IOS / 'ScreenBroadcast/SampleHandler.swift').read_text()
        self.assertIn('RPVideoSampleOrientationKey as CFString', legacy)
        self.assertIn('CapturePipeline()', legacy)
        modern = (IOS / 'Runner/SCKCaptureSession.swift').read_text()
        self.assertIn('CapturePipeline()', modern)
        self.assertIn('picker.present(using:.display)', modern)
        self.assertIn('CMSyncConvertTime(', modern)
        self.assertIn('frame[.videoOrientation]', modern)
        pipeline = (IOS / 'Shared/CapturePipeline.swift').read_text()
        self.assertIn('"X-Screen-Platform":"ios"', pipeline)
        self.assertIn('app-relay/usb-window', pipeline)
        self.assertIn('self.afterResponse = CMClockGetTime(CMClockGetHostTimeClock())', pipeline)
        # These macOS APIs are explicitly unavailable on iOS 27.
        self.assertNotRegex(modern, r'\.(?:queueDepth|minimumFrameInterval|pixelFormat|allowedPickerModes|maximumStreamCount)\s*=')

    def test_preparation_fence_native_runtime(self):
        swift = shutil.which('swift')
        if swift is None:
            self.skipTest('standalone Foundation Swift runtime unavailable; this is not an iOS build')
        source = (IOS / 'Shared/CapturePreparationFence.swift').read_text()
        check = r'''
var fence = CapturePreparationFence()
func response(_ nonce: String = String(repeating:"a",count:32), _ generation: Any = 1, _ ttl: Any = 5000) -> [String:Any] {
  ["state":"prepare","nonce":nonce,"mode":"hid","generation":generation,"expiresInMs":ttl]
}
let ready = fence.prepare(response(),requestedAt:100,now:101)
precondition(ready?.generation == 1 && ready?.deadline == 105)
precondition(ready?.body["operation"] as? String == "ready")
precondition(fence.prepare(response(),requestedAt:100,now:101) == nil) // same window cannot replay
precondition(fence.prepare(response(String(repeating:"a",count:32),2),requestedAt:100,now:101) == nil) // nonce reuse
precondition(fence.prepare(response(String(repeating:"b",count:32),1),requestedAt:100,now:101) == nil) // generation replay
precondition(fence.prepare(response(String(repeating:"c",count:32),2),requestedAt:100,now:105) == nil) // network age exhausted TTL
precondition(fence.prepare(response(String(repeating:"d",count:32),true),requestedAt:100,now:101) == nil)
precondition(fence.prepare(response(String(repeating:"e",count:32),2.5),requestedAt:100,now:101) == nil)
precondition(fence.prepare(response(String(repeating:"f",count:32),2,true),requestedAt:100,now:101) == nil)
precondition(fence.prepare(response(String(repeating:"0",count:32),2,5001),requestedAt:100,now:101) == nil)
precondition(fence.prepare(response("malformed",2),requestedAt:100,now:101) == nil)
var invalid = response(String(repeating:"1",count:32),2); invalid["mode"] = "unknown"
precondition(fence.prepare(invalid,requestedAt:100,now:101) == nil)
precondition(fence.prepare(["state":"idle"],requestedAt:100,now:101) == nil)
precondition(fence.prepare(["state":"ready"],requestedAt:100,now:101) == nil)
precondition(fence.prepare(response(String(repeating:"2",count:32),2),requestedAt:100,now:101)?.generation == 2)
print("14 preparation contract cases passed")
'''
        with tempfile.TemporaryDirectory(prefix='capture-fence-') as tmp:
            script = pathlib.Path(tmp) / 'FenceCheck.swift'
            script.write_text(source + check)
            run = subprocess.run([swift, str(script)], capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn('14 preparation contract cases passed', run.stdout)

    def test_target_dependency_embeds_extension_and_compiles_shared_contract(self):
        source = (IOS / 'Runner.xcodeproj/project.pbxproj').read_text()
        # Parse only flat OpenStep records; nested configurations do not affect graph assertions.
        objects = dict(re.findall(r'([A-F0-9]{24})\s*(?:/\*.*?\*/\s*)?=\s*\{([^{}]*)\};', source, re.S))
        refs = {key: body for key, body in objects.items() if 'isa = PBXFileReference;' in body}
        def reference(path):
            found = [key for key, body in refs.items() if f'path = "{path}";' in body]
            self.assertEqual(len(found), 1, path)
            return found[0]
        shared = [reference('Shared/CaptureContract.swift'), reference('Shared/BoundedRequest.swift'), reference('Shared/CapturePipeline.swift'), reference('Shared/CapturePreparationFence.swift')]
        for ref in shared:
            builds = [key for key, body in objects.items() if 'isa = PBXBuildFile;' in body and f'fileRef = {ref};' in body]
            self.assertEqual(len(builds), 2, 'shared Swift must belong to host and extension')
            for build in builds:
                self.assertEqual(sum(build in body for body in objects.values() if 'isa = PBXSourcesBuildPhase;' in body), 1)
        targets = [(key,body) for key,body in objects.items() if 'isa = PBXNativeTarget;' in body and 'name = ScreenBroadcast;' in body]
        self.assertEqual(len(targets), 1)
        extension_target, body = targets[0]
        self.assertIn('com.apple.product-type.app-extension', body)
        self.assertTrue(any('isa = PBXTargetDependency;' in b and f'target = {extension_target};' in b for b in objects.values()))
        self.assertRegex(source, r'dstSubfolderSpec = 13;[^}]*name = "Embed App Extensions"')
        self.assertIn('APP_BUNDLE_ID = org.example.phonecontroller;', source)
        self.assertIn('PRODUCT_BUNDLE_IDENTIFIER = "$(BROADCAST_BUNDLE_ID)";', source)
        # No private provisioning profiles or team identifier are committed.
        self.assertNotRegex(source, r'DEVELOPMENT_TEAM\s*=\s*[A-Z0-9]{10}')

if __name__ == '__main__':
    unittest.main()
