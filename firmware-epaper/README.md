# 墨水屏控制器固件

适用已实测识别的 Waveshare ESP32-S3 Touch ePaper 1.54：8MB Flash、8MB PSRAM、200×200。

本版本实现服务器额度画面的 HTTPS 拉取、变化时局刷、周期全刷、BOOT 短按翻页、长按提交停止请求，以及 USB HID+CDC 枚举。**尚未采集手机投屏、录音或执行手机控制任务。** 不生成自动鼠标/按键输入。

- 图片由 云端服务 服务器读取现有额度快照后渲染；设备不持有模型账号凭据。
- 设备请求只是传输；任务状态由服务器的 `display_service.control` 发起更新。
- `device_config.h` 只存设备专用令牌，已忽略；同样不要分发带令牌的固件二进制。
- USB 控制台：`STATUS`、`PAGE`、`STOP`；配网使用 `WIFI<TAB>SSID<TAB>PASSWORD`（不回显密码，写入已有 wifi NVS）。
- 分区保持原 NVS、OTA、assets 的地址；原始整片备份在本机受限目录，未上传 GitHub。
- 当前服务的域名解析指向另一台入口，所以固件通过 云端服务 IP 连接，仍用 `controller.example.invalid` 做 TLS SNI、证书验证和 HTTP Host；没有关闭证书校验。
- 本地 SDK 的可选 bootloader 日志 Kconfig 被先前删除，`bootloader_components/log_compat` 保存相同版本的原定义用于构建。它们来自 ESP-IDF（Apache-2.0），未修改共享 SDK。

构建：ESP-IDF 5.5.2，复制 `main/device_config.example.h` 到被忽略的 `main/device_config.h` 后填写部署配置，`idf.py build`。

屏幕驱动复用本人已有 ePaper-Dashboard 工程，补充 BUSY 超时；引脚来自本人该板配置与微雪资料。

## 当前硬件验收限制

首次刷写目标与完整备份均为原接入板（芯片序列末尾 D4:18）；随后 USB 上出现另一块芯片（末尾67:90），因此没有对其继续刷写。首次刷写已通过 esptool 写入校验，但USB枚举、屏幕显示、按钮仍待目标板重新接入实测。之后修正的停止请求网络失败重试已编译，待设备确认后刷入。
