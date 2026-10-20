# 本地屏幕确认 USB 控制

用户确认：直接在墨水屏上确认；默认不开，每次重启也关闭。

上电只枚举 CDC 串口，不包含 HID 接口；蓝牙不启动。额度/交互页保持短按翻页、长按停止，新增第三页显示 USB 控制状态及确认提示。提示实际完成屏幕绘制后才接受一次新的两秒长按，15 秒过期；短按离开即取消。禁用或停止后释放按键并切回 CDC。授权仅在 RAM 中，任何重启恢复关闭。

运行中切换 USB 使用不同 PID 的 CDC 与 CDC+HID 描述符，完整停止/重启 TinyUSB，而非只禁止发送按键；保留串口 STATUS、SAFE、REBOOT、BOOTLOADER。串口不能授予 HID 权限。USB 管理和 CDC 读写由同一个任务执行，避免切换过程中控制台访问已卸载的接口。

测试覆盖提示未显示、提示前开始按键、短按、过期、离开页面、授权后重启默认关闭和描述符接口差异。编译通过不能替代实际屏幕/USB验收。当前板已刷恢复固件且写入校验通过，运行心跳尚未验证，不直接假定屏幕驱动匹配。

## 用户补充：网络和日志

Wi-Fi默认关闭，显式WIFI ON后才启用，当次重启结束恢复关闭；USB本地4KiB日志缓存支持LOGS和watch诊断，不依赖网络。用户要求最终板子通过手机USB共享网络连接106，不能把临时USB调试当成运行联网方案。

Android待验证路线：ESP32-S3 USB Host + RNDIS网络，配合AOAv2 EP0 HID请求进行输入；主机角色同时服务网络与输入有协议基础，但手机固件对两者并用、Type-C数据/供电角色和板载硬件仍需实测。不能声称已实现；iPhone需独立协议兼容性验证。

官方依据：
- https://docs.espressif.com/projects/esp-iot-solution/en/latest/usb/usb_host/usb_rndis.html
- https://source.android.com/docs/core/interaction/accessories/aoa2
