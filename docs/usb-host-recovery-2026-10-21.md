# 通用手机 USB ADB 重启恢复：接口改造与验收

状态：用户随后改为自行手动开启ADB，暂不改硬件；本方案仅供未来参考。现板尚未改造，标准 USB ADB Host 驱动尚未实现，不能承诺重启恢复。2026-10-21 的提示音固件仍走 USB NCM + TCP5555，仅供现有链路验证。

## 产品约束与恢复边界

手机不安装 App，Wi-Fi 关闭；板端作为 USB Host，手机作为 USB Device。通过标准 ADB 接口（class FF/subclass42/protocol01）的 bulk IN/OUT 完成认证，复用每台控制板固定 RSA 密钥。不执行 adb tcpip，不依赖电脑每次开端口。首次须机主启用 USB 调试并确认“始终允许”；重启后的首次解锁、USB受限模式、厂商调试策略可能仍要求机主操作，不能由 AI 绕过。换手机必须重新授权。

现有 NCM 路线中手机是 USB Host，板端是 USB Device，底层仍需要手机 TCP5555。手机重启后端口可能关闭；持久保存配对密钥不等于端口持续开放，因此单纯重试现有 TCP 连接不能解决通用恢复。

## 推荐改造（原理连接，非已验证施工图）

保留本板屏幕、麦克风、扬声器；采用 S3 原生 USB OTG 主机。

| 接口 | 要求 |
| --- | --- |
| 数据 | S3 GPIO20 D+、GPIO19 D− 接独立 USB-A 下行母口；短差分走线及 ESD 防护 |
| 手机线 | 正常 USB-A → USB-C 数据线，手机作为外设 |
| VBUS | 稳定5V，经限流/短路保护、反向阻断开关供给下行口；不能用GPIO或3.3V供电 |
| 电源来源 | 首版优先独立5V电源并验证预算，若电池升压需另行设计和测温；不假定原板充电IC可以给手机输出5V |
| 隔离 | 主机模式隔离原 Type-C 数据路径及外部 VBUS，防止电脑/手机/外部电源互相回灌；不得将两台主机并联 |
| 调试 | 使用 J1 UART TX43/RX44/GND 与3.3V逻辑USB串口；主机运行时原生USB不能兼任CDC设备 |

原板 Type-C CC1/CC2 为5.1k下拉（R30/R46），不能靠固件把它改成完整供电主机口。不建议直接把5V灌入原Type-C VBUS再尝试；实际施工前需确认板子版本、焊接点、隔离方式和电流预算。普通有源Hub也不会自动纠正两个端口的角色。

## 待实现软件

1. 增加独立 USB Host 构建模式，与 TinyUSB DEVICE/NCM 互斥；VBUS默认关闭，驱动及电源自检通过才开启。
2. USB host daemon/client 各自负责事件；枚举复合设备中的标准ADB接口，认领双 bulk 端点；处理短包、超时、端点halt和设备拔除，禁止复用已释放transfer。
3. 将 adb_local 的 socket IO/select 抽象为传输读写与就绪事件，保留现有AUTH、typed command、观察校验和停止票据。移除主机路径对DHCP peer及5555的依赖。
4. 断线后只恢复认证传输，指数退避；旧任务及未完成输入永不重放。屏幕停止立即撤销当前任务，重连不恢复它。
5. 106网络沿用手机移动数据：在标准ADB上使用固定的 `exec:toybox nc 106.52.123.149 443` 字节隧道，板端原有TLS验证服务器证书及SNI。此方案须实机确认手机toybox nc可用；隧道失败时显示网络未就绪，不改手机Wi-Fi设置。
6. AI只在有效ADB授权和观察通道建立后协助设置导航；认证等待、未解锁、无数据线、电源异常分别提示原因。

## 实机验收顺序

- 电源工程检查：下行5V、短路保护、反灌隔离、数据角色，手机充电负载下稳定；确认后才插手机。
- 首次授权 → 读取设备标识和只读shell → 移动网络TLS → 聊天/语音 → 低风险首页/设置操作，逐项确认。
- 手机重启三次：机主首次解锁后无需电脑、无需重新打开TCP5555即可恢复；记录型号/Android版本/耗时及是否需再次授权。
- 板子重启、拔插、USB调试关闭、撤销授权、锁屏、移动网络中断分别测试；中断任务不重放。
- 运行中点STOP：停止手机后续输入及播报；重连后仍保持停止；新任务必须重新由用户发起。

参考：[Waveshare 原理图](https://github.com/waveshareteam/ESP32-S3-ePaper-1.54/blob/main/04_Hardware/Schematics/ESP32-S3-Touch-ePaper-1.54-Schematic.pdf)、[ESP32-S3 USB-OTG 开发板电源/接口参考](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-usb-otg/user_guide.html)、[ESP USB Host API与限制](https://docs.espressif.com/projects/esp-usb/en/latest/esp32s3/usb_host.html)、[AOSP ADB Wi-Fi架构](https://android.googlesource.com/platform/packages/modules/adb/+/HEAD/docs/dev/adb_wifi.md)。
