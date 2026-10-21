# Open-AutoGLM 接入进度

上游固定版本86f55382982fb054e8fc98ca80609dff8a2cdc3c，使用官方ModelClient、中文提示词及动作协议解析。独立运行环境/opt/phone-controller-autoglm-venv，不修改其他服务SDK。现有可用视觉模型mimo-v2.6-flash，连接探针已成功；没有部署AutoGLM-Phone-9B权重。

106服务端规划，板端邮箱执行；新增截图与受控中文输入命令。输入仅允许聚焦搜索框和用户原话子串，动作前复核完整当前UI，完成后需要联系人标题和独立姓名节点，拒绝无结果提示。截图编码上限768KB、ACK正文850KB；PSRAM缓冲及超时同步扩展。

IME正常输入后立即恢复；失败/可捕获中断用trap恢复，断连遗留恢复标记，下次ADB连接先恢复，恢复前阻止新任务。断线当下不能保证立刻恢复，应如实提示待重连恢复。

17项固件主机测试、85项Python测试通过。审查发现并修复expire缩进和“未找到”误报成功问题。小米实测：微信搜索框已写入李洋，结果包含联系人标题及独立李洋节点，默认IME恢复豆包，结果页保留。这是Mac诊断调用，与板端语音验收分开。首次无等待时文字未写入；按官方切换/清空/输入/恢复等待后成功，固件已修正。

完整云端规划器桥接测试因手机前台从豆包变化到饿了么而停止，没有重放动作，已请求用户暂停操作和其他自动化任务。ci57云端构建中；服务端代码已部署但EPAPER_PHONE_BACKEND=legacy，待新固件升级再启用autoglm。原服务代码备份/var/backups/phone-controller/before-autoglm-20261021.tar.gz，运行环境drop-in /etc/systemd/system/phone-controller-display.service.d/10-autoglm-runtime.conf。

## 用户最新修正，取代上方执行架构

Open-AutoGLM仅参考规划，HID鼠标负责所有点击/移动/拖动；ADB只允许中文输入。截图必须走另一条USB投屏通路。ci57已取消，没有刷入；服务器EPAPER_PHONE_BACKEND=hid_pending，手机任务明确播报当前未执行，避免落回旧ADB执行器。ci55仍在板上，保留已验证的语音/触摸功能。

官方资料：Xiaomi17Ultra FAQ声明支持DP1.4 Alt Mode（https://www.mi.com/global/support/faq/details/KA-667490/）。微雪现板资料未提供DP/HDMI视频接收硬件（https://docs.waveshare.com/ESP32-S3-ePaper-1.54）。scrcpy OTG/HID免ADB模式明确禁用音视频（https://github.com/Genymobile/scrcpy/blob/master/doc/otg.md）。USB鼠标与USB视频采集必须分开验证，当前不能声称现板仅插数据线即可接收DP投屏。


## 2026-10-21：按 USB 视频 + AOA HID 收敛

确认 Open-AutoGLM 仅作截图理解和动作规划参考。点击、移动、拖动使用板端 USB HID；ADB 只用于获准的 ADB Keyboard 中文输入，并在输入后恢复原输入法。固件 ADB 命令层已收紧为只接受 type_text，删除截图、UI 观察、启动应用、tap、swipe 和设置命令；服务端当前 hid_pending 继续拒绝手机操作，直到新视频与 HID 链路实测通过。

Android 官方 AOA 2.0 支持 accessory+ADB 配置，同时通过控制传输注册 HID、发送鼠标/键盘事件。该模式中板端为 USB 主机、手机为 accessory；与当前 S3 固件的 USB 外设 HID 描述符是不同实现。Xiaomi 17 Ultra 支持 DP 1.4 Alt Mode，但视频采集还需 USB-C PD/DP Alt Mode 协商与布线、DP 转 HDMI 接收、HDMI-to-MIPI CSI 采集（例如 HDMI 接收桥 + P4 CSI 摄入），以及维持 USB2 AOA/ADB 的同一配件链路。EDID只声明显示能力，不采集像素。正式集成需先验证 DP、AOA HID、ADB Keyboard 三者同线并发和供电，再选定采集桥与PCB。

现有 Waveshare S3 1.54-inch e-paper board 没有 DP/HDMI 接收输入，因此没有板端视频帧来源。不能以 Mac scrcpy、ADB screencap、电脑转发或无线投屏充当验收。下一阶段先做外置实验链路：USB-C DP Alt Mode → HDMI 接收 → CSI/P4 capture；AOA host 单独验证 HID 与 ADB 的并发；通过后再设计可集成版载板/主板。当前固件保留已验收语音与屏幕交互；没有给旧 S3 刷入未验证 HID/视频固件。
