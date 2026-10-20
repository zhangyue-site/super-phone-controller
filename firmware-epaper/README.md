# 墨水屏控制器固件

适用已实测识别的 Waveshare ESP32-S3 Touch ePaper 1.54：8MB Flash、8MB PSRAM、200×200。

本版本实现服务器额度画面的 HTTPS 拉取、变化时局刷、周期全刷、BOOT 短按翻页、长按提交停止请求，以及默认仅 CDC、经本地屏幕确认后才开启 HID 的 USB 模式。**尚未采集手机投屏、录音或执行手机控制任务。** 不生成自动鼠标/按键输入。

- 图片由 云端服务 服务器读取现有额度快照后渲染；设备不持有模型账号凭据。
- 设备请求只是传输；任务状态由服务器的 `display_service.control` 发起更新。
- `device_config.h` 只存设备专用令牌，已忽略；同样不要分发带令牌的固件二进制。
- 每次启动关闭 HID、蓝牙和 Wi-Fi，不保存上次授权。默认 USB 描述符仅含 CDC，不出现键盘接口。
- BOOT 短按依次切换额度、交互、USB 控制页；确认页绘制成功后，在15秒内重新长按BOOT两秒并松开才能开启/关闭HID，短按取消。其他页长按仍停止并撤销HID。
- Wi-Fi 仅手动 `WIFI ON` 开启，`WIFI OFF` 关闭；连接手机热点也需要开启Wi-Fi。手机USB共享网络尚未接入本固件。
- USB 控制台：`STATUS`、`LOGS`、`PAGE`、`STOP`、`SAFE`、`REBOOT`、`BOOTLOADER`；配网使用 `WIFI<TAB>SSID<TAB>PASSWORD`（不回显密码，写入已有 wifi NVS）。
- 分区保持原 NVS、OTA、assets 的地址；原始整片备份在本机受限目录，未上传 GitHub。
- 当前服务的域名解析指向另一台入口，所以固件通过 云端服务 IP 连接，仍用 `controller.example.invalid` 做 TLS SNI、证书验证和 HTTP Host；没有关闭证书校验。
- 本地 SDK 的可选 bootloader 日志 Kconfig 被先前删除，`bootloader_components/log_compat` 保存相同版本的原定义用于构建。它们来自 ESP-IDF（Apache-2.0），未修改共享 SDK。

构建：ESP-IDF 5.5.2，复制 `main/device_config.example.h` 到被忽略的 `main/device_config.h` 后填写部署配置，`idf.py build`。

屏幕驱动复用本人已有 ePaper-Dashboard 工程，补充 BUSY 超时；超时后停用屏幕而不重启芯片，保留USB诊断；引脚来自本人该板配置与微雪资料。

## 当前硬件验收限制

原板（MAC末尾D4:18）已恢复下载连接，最小恢复固件已刷入并收到3秒间隔的连续心跳。随后已写入第一版默认CDC的确认固件，真机STATUS返回 `usb=1 hid=0 bluetooth=0 screen_error=1`，PID为0x4001；屏幕驱动故障被隔离，未因屏幕超时重启。屏幕确认、授权后的USB重枚举与重启后关闭仍待实机验收，不能仅凭构建通过宣称完成。

默认Wi-Fi关闭及LOGS缓存的版本已写入，真机返回 `wifi=0 wifi_enabled=0 usb=1 hid=0 bluetooth=0`，LOGS完整读出缓存。读到屏幕BUSY从0变1后约20ms报超时，定位到原驱动5ms延时在100Hz调度下变成0 tick，循环计数并非真实10秒；修正版改用esp_timer真实10秒截止时间并每次至少等待1 tick，待写入并验证屏幕。

`esptool --after watchdog_reset`已成功从原生下载模式启动应用；普通RTS hard_reset曾持续回到下载模式。BOOTLOADER命令后的USB重枚举仍未可靠通过，不能当作已验证的软件恢复入口；修正版将在USB断开、卸载TinyUSB后把共享PHY交还USB-Serial/JTAG，再进入ROM，仍待实测。

`python3 tools/board_console.py status` 查看状态，`logs`读取最近4KiB日志，`watch --seconds 20`循环读取状态和日志。只自动选择唯一的Epaper Phone Controller，避免误操作M5stack。日志保存在RAM，重启清空，不上传服务器；固件不记录Wi-Fi密码或Bearer令牌。

## 官方烧录与恢复方法（2026-10-20核对）

本系列侧键为 BOOT 与 PWR，没有依据要求用户寻找 RST/RESET。官方 FAQ：按住 BOOT，重新上电进入下载模式。

1. 断开 USB；带电池时先用 PWR 关闭电池供电，确保芯片实际断电（墨水屏断电后仍能保留图像，不能靠图像判断是否关机）。
2. 按住 BOOT 不放，再接入 USB 数据线上电，待电脑出现下载串口后松开 BOOT。
3. 按本项目保留原NVS/资产布局的地址烧写，成功后松开 BOOT 并重新上电运行。

官方：https://docs.waveshare.net/ESP32-S3-ePaper-1.54/FAQ/
硬件：https://docs.waveshare.com/ESP32-S3-ePaper-1.54

PWR为GPIO18输入，电池供电保持为GPIO17输出。新固件已修正GPIO18方向，并增加PWR长按1.5秒关闭电池供电保持；插着USB时USB仍可继续供电。
