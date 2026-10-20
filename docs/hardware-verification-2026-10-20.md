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

## 补充验证

串口发送HID ON被拒绝并提示仅允许本地屏幕确认，随后STATUS仍为hid=0；重启和本轮检查期间未出现新的水墨屏键盘识别记录。

## 限制

用户已回复“能看到，显示正常”，实际屏幕显示通过目视验收。开启HID后的重枚举和撤销、开启后重启、最终软件BOOTLOADER路径、手机USB共享网络、手机画面采集与控制，均不包含在本次已通过范围内。默认关闭Wi-Fi时服务器离线符合当前设置，最终运行仍需接入手机网络。

## USB 本地网络检查页新版

已刷入本地网络测试版并通过所有写入区域哈希校验。语音页长按两秒启动八项清单：USB、地址、ADB、手机共享网络、106、AI对话、语音识别、完成。仅全部通过显示“超级手机助手已经在线”。

106 已部署认证的 /checks 与 /checks.bin；对话使用实际模型请求，语音使用合成测试句调用实际识别服务。两项独立返回成功；这不表示手机执行器已接入。服务就绪响应明确保留 phoneControlReady=false。

刷后板端 STATUS：wifi=0 wifi_enabled=0 hid=0 bluetooth=0 screen_error=0 adb=0。麦克风诊断16000样本、RMS164.5、峰值635，数据丢弃无上传。32项Python测试和原生preflight测试通过；本地网络版与默认版编译通过。

待验收：手机直连取得本地地址、ADB连接、共享网络与服务器端到端链路。目前本地模式只提供局域网DHCP，不提供互联网路由，尚未实现通过ADB自动切换共享网络；语音页此版本先执行准备检查，不会绕过网络前置条件录音或控制手机。手机重启后ADB自动恢复也未验证。

## 触屏首页版

已核对同一板MAC并刷入触屏首页版，各区域哈希通过。启动日志识别 FT6336@0x38，约3.4秒完成首页（page=5）刷新。STATUS仍wifi=0 wifi_enabled=0 hid=0 bluetooth=0 screen_error=0。共用I²C后麦克风再次诊断16000样本，RMS179.8、峰值730，音频丢弃无上传。默认版、本地网络版编译及32项Python测试、原生触摸状态测试通过。

新增开机触屏入口、底部导航和本地触屏长按确认。读数异常/多指后锁定到确认抬手；刷新、页面变化和断线令旧触摸失效。等待用户实际轻触“开始检查”，验收坐标方向和按钮切换；不得将芯片探测成功等同于触摸操作已验收。
