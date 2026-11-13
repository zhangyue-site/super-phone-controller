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
            self.assertIn('263c8120640db90889073a23cfd3e77dd64f5ca068ac23eea27185f5eaa4be13', job)
            self.assertIn('45484096aa3e90b0d3e6b4caf3d94311505d1193972c028675149129d757dbe2', job)
            self.assertLess(job.index('Restore pinned bundled model'), job.index('flutter pub get'))

    def test_no_failed_test_packaging_or_paid_runner(self):
        self.assertNotIn('continue-on-error', self.workflow)
        self.assertNotIn('available for diagnosis', self.workflow)
        self.assertNotIn('self-hosted', self.workflow)
        self.assertNotIn('runs-on: xcode-27-xlarge', self.workflow)
        self.assertNotIn('runs-on: macos-latest-large', self.workflow)
        self.assertIn('runs-on: xcode-27', self.ios)

    def test_native_sdk_requirement_and_encryption_remain_explicit(self):
        self.assertIn('xcrun --sdk iphoneos --show-sdk-version', self.ios)
        self.assertIn('iOS27 simulator required', self.ios)
        for job in (self.android, self.ios):
            self.assertIn('PRIVATE_ARTIFACT_PASSWORD', job)
            self.assertIn('-mhe=on', job)
            self.assertIn('BUILD_NAME', job)
            self.assertIn('BUILD_NUMBER', job)


if __name__ == '__main__':
    unittest.main()
