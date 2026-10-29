#pragma once
namespace controller {
enum ExecCode { EXEC_READY = 0, EXEC_NO_USB = 1, EXEC_OFFLINE = 2, EXEC_NO_HID = 3, EXEC_FAILED = 4 };
inline int exec_status(bool usb, bool online, bool hid, bool failed) {
 if (failed) return EXEC_FAILED;
 if (!usb) return EXEC_NO_USB;
 if (!online) return EXEC_OFFLINE;
 if (!hid) return EXEC_NO_HID;
 return EXEC_READY;
}
}
void controller_exec_show(int code);
void controller_exec_fail();
void controller_exec_clear();
bool controller_exec_failed();
