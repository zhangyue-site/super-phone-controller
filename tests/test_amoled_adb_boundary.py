"""AMLite NCM-ADB architecture boundary test (ported from epaper
tests/test_adb_observation.py, task ncm-amlite-usblocaladb).

The board's ADB bridge is INPUT-ONLY: the only command is TYPE_TEXT (keyboard
text injection via ADBKeyboard broadcast). No screen capture, no touch
injection, no observation/parsing of the phone. Enforced at source level so
the invariant survives refactors. The board must stay blind: it types, it
never looks.
"""
import unittest
from pathlib import Path

import re

COMP = Path(__file__).resolve().parents[1] / "firmware-amoled/components/controller_usb_local"

FORBIDDEN = ("screencap", "screenshot", "input tap", "input swipe",
             "input keyevent --longpress", "am start", "dumpsys activity",
             "uiautomator", "OBSERVE", "SCREENSHOT", "TAP_COMMAND", "SWIPE", "LAUNCH")


def strip_comments(src):
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub("//[^\n]*", "", src)

class AdbBoundaryTests(unittest.TestCase):
    def test_op_enum_input_only(self):
        s = (COMP / "adb_command.h").read_text()
        self.assertIn("enum class AdbOp {TYPE_TEXT};", s)
        for f in FORBIDDEN:
            self.assertNotIn(f, s)

    def test_cloud_pipe_pinned_to_single_relay(self):
        code = strip_comments((COMP / "adb_local.cpp").read_text())
        self.assertLessEqual(code.count("106.52.123.149"), 1)

    def test_transport_implements_type_text_only(self):
        s = strip_comments((COMP / "adb_local.cpp").read_text())
        self.assertIn("TYPE_TEXT", s)
        for f in FORBIDDEN:
            self.assertNotIn(f, s)

    def test_identity_header_ignored_by_git(self):
        gi = (COMP / ".gitignore").read_text()
        self.assertIn("device_adb_keys.h", gi)

    def test_no_hidden_sources_added(self):
        srcs = sorted(p.name for p in COMP.glob("*.cpp"))
        self.assertEqual(srcs, ["adb_local.cpp", "usb_network.cpp"])


if __name__ == "__main__":
    unittest.main()
