#!/usr/bin/env python3
"""Offline bundle/extension wiring checks, not an iOS build or device test."""
import pathlib
import plistlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
IOS = ROOT / 'app' / 'ios'

class IOSCaptureContract(unittest.TestCase):
    def plist(self, path):
        with (IOS / path).open('rb') as stream:
            return plistlib.load(stream)

    def test_extension_configuration_and_group_agree(self):
        host = self.plist('Runner/Info.plist')
        extension = self.plist('ScreenBroadcast/Info.plist')
        self.assertEqual(host['CaptureAppGroup'], extension['CaptureAppGroup'])
        self.assertEqual(host['ControllerBaseURL'], extension['ControllerBaseURL'])
        self.assertEqual(host['BroadcastExtensionID'], '$(BROADCAST_BUNDLE_ID)')
        for target in ['Runner', 'ScreenBroadcast']:
            self.assertEqual(self.plist(f'{target}/{target}.entitlements')['com.apple.security.application-groups'], [host['CaptureAppGroup']])
        self.assertEqual(extension['NSExtension'], {
            'NSExtensionPointIdentifier': 'com.apple.broadcast-services-upload',
            'NSExtensionPrincipalClass': '$(PRODUCT_MODULE_NAME).SampleHandler',
            'RPBroadcastProcessMode': 'RPBroadcastProcessModeSampleBuffer',
        })

    def test_usb_snapshot_matches_nullable_dart_contract(self):
        native = (IOS / 'Runner/NativeBridge.swift').read_text()
        self.assertRegex(native, r'if call.method == "snapshot" \{ reply\(nil\); return \}')
        self.assertIn('"usb_unsupported"', native)
        dart = (ROOT / 'app/lib/usb_launch.dart').read_text()
        self.assertRegex(dart, r'value\s*==\s*null\s*\?\s*null\s*:\s*UsbAttachment.parse')

    def test_target_dependency_embeds_extension_and_compiles_shared_contract(self):
        source = (IOS / 'Runner.xcodeproj/project.pbxproj').read_text()
        # Parse only flat OpenStep records; nested configurations do not affect graph assertions.
        objects = dict(re.findall(r'([A-F0-9]{24})\s*(?:/\*.*?\*/\s*)?=\s*\{([^{}]*)\};', source, re.S))
        refs = {key: body for key, body in objects.items() if 'isa = PBXFileReference;' in body}
        def reference(path):
            found = [key for key, body in refs.items() if f'path = "{path}";' in body]
            self.assertEqual(len(found), 1, path)
            return found[0]
        shared = [reference('Shared/CaptureContract.swift'), reference('Shared/BoundedRequest.swift')]
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
