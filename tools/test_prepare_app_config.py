import unittest
from prepare_app_config import prepare

class ReleaseConfigTests(unittest.TestCase):
    def test_missing_base_never_uses_a_fallback(self):
        with self.assertRaisesRegex(ValueError, "CONTROLLER_BASE_URL"):
            prepare({"CONTROLLER_APPLICATION_ID": "org.example.test"})
    def test_bad_urls_are_rejected_without_echoing_values(self):
        for url in ("http://controller.test", "https://user:secret@controller.invalid", "https://controller.test?token=secret", "https://controller.test#secret"):
            with self.subTest(url=url):
                with self.assertRaises(ValueError) as caught:
                    prepare({"CONTROLLER_BASE_URL": url, "CONTROLLER_APPLICATION_ID": "org.example.test"})
                self.assertNotIn("secret", str(caught.exception))
    def test_download_optional_but_configured_url_is_validated(self):
        env={"CONTROLLER_BASE_URL":"https://controller.test/api/", "CONTROLLER_APPLICATION_ID":"org.example.test"}
        self.assertEqual(prepare(env), {"CONTROLLER_BASE_URL":"https://controller.test/api"})
        with self.assertRaisesRegex(ValueError, "CONTROLLER_DOWNLOAD_URL"):
            prepare(dict(env, CONTROLLER_DOWNLOAD_URL="http://download.test"))
    def test_package_identity_required(self):
        with self.assertRaisesRegex(ValueError, "CONTROLLER_APPLICATION_ID"):
            prepare({"CONTROLLER_BASE_URL":"https://controller.test"})
if __name__ == "__main__":
    unittest.main()
