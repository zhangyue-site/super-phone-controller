"""Offline CI contract checks; these do not claim a hosted build passed."""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class AppBuildWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = (ROOT / '.github/workflows/app-build.yml').read_text()
        cls.android, cls.ios = cls.workflow.split('  android:\n', 1)[1].split('  ios:\n', 1)

    def test_both_platforms_restore_identical_pinned_asset_before_flutter(self):
        for job in (self.android, self.ios):
            self.assertIn('Restore pinned bundled model', job)
            self.assertIn('7310ba7d56a24833297e5e128aaa9981090c45f7701889ad09c31fad4c971c37', job)
            self.assertIn('45a522a4e47102e32aa6b447e470598012556ef0d37226fc3f793e162a0f8491', job)
            self.assertIn('assets/controller-button.onnx', job)
            self.assertNotIn('bt_v10_int8.onnx', job)
            self.assertLess(job.index('Restore pinned bundled model'), job.index('flutter pub get'))

    def test_no_failed_test_packaging_or_paid_runner(self):
        self.assertNotIn('continue-on-error', self.workflow)
        self.assertNotIn('available for diagnosis', self.workflow)
        self.assertNotIn('self-hosted', self.workflow)
        self.assertNotIn('runs-on: xcode-27-xlarge', self.workflow)
        self.assertNotIn('runs-on: macos-latest-large', self.workflow)
        self.assertIn('runs-on: xcode-27', self.ios)

    def test_simulator_boot_has_own_budget_and_build_is_diagnosable(self):
        self.assertIn('name: Boot iOS 27 simulator', self.ios)
        self.assertIn('timeout-minutes: 30', self.ios)
        self.assertIn('flutter test integration_test/startup_test.dart -v', self.ios)
        self.assertIn('name: Preserve simulator diagnostics', self.ios)
        self.assertIn('if: failure()', self.ios)

    def test_android_release_preserves_existing_store_package_and_usb_tests(self):
        self.assertIn('CONTROLLER_APPLICATION_ID: org.example.phonecontroller', self.android)
        self.assertIn('test_usb_control_auth.py', self.workflow)

    def test_native_sdk_requirement_and_encryption_remain_explicit(self):
        self.assertIn('xcrun --sdk iphoneos --show-sdk-version', self.ios)
        self.assertIn('../tools/select_ios_simulator.py', self.ios)
        for job in (self.android, self.ios):
            self.assertIn('PRIVATE_ARTIFACT_PASSWORD', job)
            self.assertIn('-mhe=on', job)
            self.assertIn('BUILD_NAME', job)
            self.assertIn('BUILD_NUMBER', job)


if __name__ == '__main__':
    unittest.main()
