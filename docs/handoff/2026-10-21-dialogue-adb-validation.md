# 对话、播报与本地 ADB 验证

当前实现：106负责ASR、连续对话上下文、手机步骤决策、结果TTS和大字结果位图；控制板通过自己的USB本地ADB执行，每次输入前再次读取界面，变化或锁屏未知即停止。HTTPS关闭后才执行ADB，未知结果不重发。屏幕大区域停止会撤销ADB授权ticket、对话和播放；旧worker释放资源后可重新开始。静音跳过播报，音量不改变录音增益。

## ADB调查结论

- 106的旧cardputer-phone中继服务运行，但专用ADB `127.0.0.1:15565` 的目标小米 `25128PNA1C` 为offline。旧视频和执行记录超过一天，旧导航结果为Phone locked，不能证明当前可控制。
- 本地先前识别的小米地址192.168.7.235:5555连接超时；当前USB串口为M5stack，不是Waveshare目标板，未刷写它。其他在线ADB设备均未操作。
- 现方案为板子USB NCM本地网络到手机TCP5555，不是原生USB Host ADB。它依赖手机已开启ADB TCP端口及RSA授权。普通无root固件不能在手机重启后凭空开启关闭的adbd端口；现在明确显示端口未开/授权失败/超时/断开。
- 不能把旧中继的offline设备、模拟界面测试或固件编译当成实际USB手机控制通过。

## 已通过

- 15组固件主机回归，含ADB分包/窗口、命令白名单/坐标/退出标记、停止代数、执行和播报停止后可重启。
- 61项Python回归，含真正运行固件中的观察shell脚本（模拟Android命令）、未知锁屏拒绝、前后台改变拒绝、节点导航限制、命令仅交付一次、重复ACK拒绝、跨设备隔离、停止旧回合、TTS失败不续听、语音上传/任务创建锁回归。
- ESP-IDF 5.5.2本地固件 `2026.10.21-dialogue` 编译通过；IDF6改用条件cJSON依赖。
- 106隔离服务实际调用现有模型与小米TTS：两轮姓名记忆成功，生成实际16kHz单声道PCM和5000字节位图。
- 106实际模型+模拟UI：打开设置经过observe/observe/tap/observe，收到新设置界面后才报告完成。模拟手机，未实际点击手机。
- 106实际ASR测试录音识别后完成聊天和TTS，ASR约0.7秒；整轮还需模型与TTS时间，不能代表板子实测延迟。
- 106原Edge TTS返回403，已改用现有小米语音配置；不增加或公开密钥。

## 部署与待验收

106展示服务已备份并更新；备份 `/opt/phone-controller-backups/20261021T041900Z-dialogue`。保留旧语音客户端的仅ASR行为，新固件使用X-Voice-Dialogue明确开启新链路。不调用旧中继执行器。

目标Waveshare板与小米目前未识别在线，尚未刷入本次固件，以下仍待实机：USB直连授权/断连恢复、打开设置与返回桌面验证、操作中屏幕停止、实际麦克风与扬声器、静音与音量、长时稳定性和耗电。未发布到自动OTA通道，未合并PR。

单回合180秒、最多8次决策/6次输入、ADB单命令12秒、15秒失联取消。连续输入单轮10秒，最多12轮；90毫秒脉冲不会被当作有效语音。允许导航与查看，发送、支付、删除、授权、登录等不在本次自动执行范围。

接口及手机连接要求见 display_service/README.md；手机操作的证据为新UI，不是模型口头声称。

106正式服务SNI/TLS烟测通过：测试回答、40960字节PCM、5000字节位图及停止均成功。外部直连固定106 IP并验证域名证书返回预期401（未带令牌），与板端固定IP通道一致。默认域名解析路径此次返回404，未将其算作固定ADB代理通道失败，也未改其他域名路由。Flutter再次通过静态分析与5项测试。

依据：[Android ADB Wi-Fi架构](https://android.googlesource.com/platform/packages/modules/adb/+/HEAD/docs/dev/adb_wifi.md)、[ADB协议](https://android.googlesource.com/platform/packages/modules/adb/+/refs/heads/main/docs/dev/protocol.md)、[MiMo TTS](https://mimo.mi.com/docs/en-US/quick-start/usage-guide/audio/speech-synthesis-v2.5)、[IDF6 cJSON迁移](https://docs.espressif.com/projects/esp-idf/en/v6.0/esp32c3/migration-guides/release-6.x/6.0/protocols.html)。

打开App使用手机实际启动Activity白名单，不点击任意桌面小组件。观察元数据只从XML外头尾读取，UI文字不能伪造LOCKED/LAUNCHER。启动后导航仍核对目标包，桌面图标不算已打开。IDF6的75be999/12afd3e构建通过，最终launch增强固件f090054的IDF6构建39544498478也已通过。

模型结构输出异常会在本回合8次决策预算内修正：空reply不播报；done必须提供最新UI原文，修正证据不重放输入。模型若跳过首次观察，执行器强制先只读观察并要求重新规划，不执行猜测的启动入口。新增回归覆盖这些真实106联调问题。

正式Nginx流式验收发现并修复：代理把3200字节小块合并成超过32768字节的块，旧解析器返回422。现在按整段320000字节上限校验，接受合法合并块，仍拒绝超总量、截断和非法帧。正式TLS `/voice/stream` 上传52714字节测试音频返回200，ASR→聊天→TTS成功，返回143360字节PCM及5000字节位图；停止后poll返回409。新增三项代理合块/总量/截断回归。

最终：61项Python、15组主机逻辑、5项Flutter测试与Dart分析通过；IDF5.5及IDF6构建通过。61项Python在本地运行，IDF6构建对应固件源码f090054；后续提交只修改服务器、测试和验证记录。独立审查未发现阻塞问题。
