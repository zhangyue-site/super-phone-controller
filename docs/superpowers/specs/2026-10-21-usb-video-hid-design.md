# USB 视频与 AOA HID 手机控制设计

日期：2026-10-21
状态：硬件可行性阶段；当前 S3 板没有视频接收器，服务端手机操作保持停用。

资料依据：[Android Open Accessory 2.0](https://source.android.com/docs/core/interaction/accessories/aoa2)、[小米 DP 1.4 Alt Mode 说明](https://www.mi.com/global/support/faq/details/KA-667490/)、[TC358743 驱动参考](https://github.com/espkvm/espkvm/tree/main/components/tc358743)、[微雪现板资料](https://docs.waveshare.com/ESP32-S3-ePaper-1.54)。

## 目标

用 Open-AutoGLM 的规划协议分析实时手机画面。所有导航点击、指针移动和拖动由控制器通过 USB HID 完成。ADB 仅使用 ADB Keyboard 输入用户明确说出的中文；输入后恢复原输入法，手机留在结果页。STOP 立即取消后续动作并释放所有 HID 按键。

## USB 连接角色

Android Open Accessory 2.0 的 accessory+ADB 配置允许配件主机和手机 accessory 同时使用 ADB；AOAv2 HID 通过控制传输注册和发送 HID 报告，不要求手机枚举控制板的普通 HID 外设。该方案与当前 ESP32-S3 USB 外设固件不同，需要 USB host/AOA 实现及目标小米实测。

目标 Xiaomi 17 Ultra 支持 DP 1.4 Alt Mode。USB-C 视频链路仍需 PD/Alt-Mode 协商、DP lane 信号完整性及接收芯片。EDID/显示器诱骗只会使手机输出视频，不会读取/解码帧。

## 实验链路

手机 USB-C 同时保留 USB2 数据并输出 DP Alt Mode。配件侧包含：

1. USB-C DRP/PD 控制器：协商 DP Alt Mode，处理角色、CC、供电和保护。
2. DP 接收/转 HDMI 桥：把 DisplayPort lane 变为标准 HDMI 时序；明确支持手机源端输出格式。
3. HDMI-to-MIPI CSI 接收器（TC358743 类）和 ESP32-P4 capture board：采集解码帧；先实验板，不直接声称能接现有 S3 板。
4. USB host/AOA 2.0 控制器：和手机 accessory+ADB 同线工作，通过 AOAv2 HID 报告发相对鼠标事件；ADB仅执行获准的 ADB Keyboard 输入。
5. P4 至现有 S3 的帧/控制桥（SPI 或并行摄入需测带宽），或把 P4 作为主板并保留 S3 仅作 e-paper/音频外设。选择之前先测帧压缩与链路带宽。

预期图像链路：手机 DP → DP-to-HDMI → HDMI-to-CSI → P4 摄入/压缩 → 规划服务。操作链路：语音 → 规划服务 → 受限动作 → AOA HID mouse。输入链路：聚焦搜索框经画面确认 → USB ADB Keyboard 广播中文 → 恢复原 IME。图像不得通过 ADB 获得。

## 阶段验收

- 小米 17 Ultra 在 Wi-Fi 关闭时输出稳定 DP 视频；USB 数据/充电状态可解释。
- 同一线缆与一次 AOA 会话中，手机维持 accessory+ADB；ADB Keyboard 可输入后恢复原 IME。
- AOA HID 鼠标可移动、点击、拖动；采用初始相对指针时需校准并验证屏幕坐标误差。
- CSI/P4 可连续采集带分辨率、时间戳和丢帧计数的视频帧；视觉服务仅消费此来源。
- 用户任务“打开微信找到李洋”停在搜索结果页，播报结果；不发消息；点击结果页不属于本任务。
- STOP 后释放鼠标按钮、取消任务，不重放过期动作。
- 已装 S3 板在没有外置/集成视频链路时必须报告“采集硬件未接入”，不进入手机动作。

## 关键限制

- 现有 Waveshare S3 e-paper board 只有 USB device 固件路径，没有 DP 接收芯片、CSI 接口或 USB host/AOA 当前实现。
- ESP32-P4 + HDMI-to-CSI 可接收 HDMI，但手机 DP 输出到 HDMI 还需要 DP 接收/转换以及 USB-C PD/Alt-Mode 设计。
- 任何芯片搭配、USB 复用、供电预算和机械形态都必须在实验板上实测后再定版；当前没有购买清单或已验收样机。
