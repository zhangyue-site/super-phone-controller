# 水墨屏恢复与默认关闭验收（2026-10-20）

目标为已备份原板，MAC仅记录末尾D4:18。固件SHA256：`798ee0a43bfa819d81bf5fba2b330fee56e146a098dbad1d1091e1acaf5b5fa6`。原NVS/assets保留，固件和完整备份不上传。

## 弹窗归属

从Mac loginwindow的KeyboardSetupAssistant分类日志读取KeyboardServiceAddedCallback及紧邻的Unknown KeyboardAdded/launch记录，不以猜测或设备当前是否在线作为归属依据：

- 16:47:34、16:47:41、16:52:16、16:56:35、16:56:41：Epaper Phone Controller，USB，VID 0x303A / PID 0x4005；为旧版默认HID固件。
- 17:39:18：zy_de_aibao，Bluetooth Low Energy，报送VID/PID均为0，紧接着启动识别助理。
- 17:40:01：Korea4-A1F58C，Bluetooth Low Energy，报送VID/PID均为0，紧接着启动识别助理。17:46:04设备断开与助理的键盘断开回调时间一致。

未删除Mac键盘识别记录、未修改蓝牙配对。没有保存蓝牙地址或整份系统日志。

## 刷写和重启

1. 下载模式读取芯片身份，匹配原板；保持下载状态后直接刷写修正版，所有区域Hash verified。
2. 使用watchdog_reset启动应用，读取STATUS：`wifi=0 wifi_enabled=0 usb=1 hid=0 bluetooth=0 page=0 stopped=0 screen_error=0 psram=8388608`。
3. 实际IORegistry设备PID 0x4001；接口class仅2、10，无3。
4. 通过串口REBOOT正常软件重启，读取新启动日志reset_reason=3；相同关闭状态与无HID接口再次验证。屏幕在启动约3.1秒完成刷新。

## 限制

实际画面外观待用户目视确认。开启HID后的重枚举和撤销、开启后重启、最终软件BOOTLOADER路径、手机USB共享网络、手机画面采集与控制，均不包含在本次已通过范围内。默认关闭Wi-Fi时服务器离线符合当前设置，最终运行仍需接入手机网络。
