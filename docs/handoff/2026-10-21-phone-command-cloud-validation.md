# 手机指令通路与云端升级验证（2026-10-21）

## 用户最终范围

手机ADB可由用户手动开启，屏幕给出明确提示；不改USB Host硬件、不装手机App、不启用Wi-Fi。用户先验收软件，稍后接手机直连实测。后续开发和修复在106云端工作区，固件由GitHub Actions构建、106私有OTA发布。

## 已定位并修正

- 实际小米Android17执行旧观察脚本：exit0、6058字节却没有XML，无法进入手机导航；uiautomator独立进程向/proc/self/fd/1写入不等于父进程stdout。改用umask077唯一临时文件、compressed dump、检查非空后cat、trap清理。
- 同一实际手机的新脚本：2.85秒、37607字节、71个节点、128个启动入口，剩余临时文件0。当前手机走Wi-Fi，只作只读兼容性诊断，不是板手机无Wi-Fi直连验收，也没有执行真实手机输入。
- verbose Activity输出先筛有效组件再head128，修正只剩约42个入口的问题；服务命令缓冲扩大到2048并有长度测试。
- 原ADB worker在任何业务失败后关闭承载HTTPS的同一ADB连接，导致ACK和TTS无法返回。现仅真实传输损坏才关闭，界面变化/找不到App等拒绝保留通道；STOP仍撤销票据。未知输入结果不自动重发。
- ACK加入白名单错误code，106转为具体中文结果和TTS。日志只记录op、id前缀、耗时、字节数和结果，不打印UI或令牌。屏幕明确提示手动开启5555，USB调试开关本身不保证端口已开。

## 已完成验证

106云端73项Python测试、17组C/C++主机回归通过。覆盖真实Android写文件行为、临时文件清理、verbose列表、从语音HTTP上传到命令ACK/失败TTS/屏幕/STOP的贯通回归，以及私有发布、损坏镜像拒绝、旧版本保留、旧构建禁止覆盖新版本。

106真实ASR/模型/TTS、模拟手机执行：第一轮 observe→observe→launch→observe，done，结果PCM51200字节、屏幕5000字节；第二轮 observe→observe→launch后回报screen_changed，error，具体失败语音163840字节、屏幕5000字节。两轮STOP后poll409，未重放输入。输入为合成“打开手机设置”音频，不是用户现场麦克风录音。记录 `/tmp/controller-cloud-path-smoke.log`。

106在线服务已备份并更新app/conversation/dialogue/firmware，systemd active；备份 `/opt/phone-controller-backups/20261021-command-cloud-4f1674e`。正式SNI/TLS固件下载鉴权与旧current镜像哈希通过。

云端工作区 `/opt/phone-controller-workspace`，仓库限定写入deploy key；OTA独立SSH key强制固定epaper-01发布命令、restrict禁止shell和转发；CI固定主机公钥。镜像验证芯片/项目/版本/段/XOR/SHA/容量，按哈希不可变保存、current原子切换、previous保留，main才自动发布。云端后续约定写入AGENTS.md及.cursor规则。

## 待追加

云端ESP-IDF6编译与本轮新版本发布结果见下方追加记录。用户稍后的真实手机直连、ASR后实际导航、STOP、断线和实际OTA下载/重启回报尚未验收，不以模拟测试或云端发布替代。

## 云端构建与正式OTA发布

GitHub Actions run39565196734（源码4f1674e，构建序号52）官方ESP-IDF6编译成功，版本/容量校验通过。受限SSH发布器已将 `2026.10.21-ci52` 激活到epaper-01私有OTA：1799248字节，SHA256 `6873bf579c1dc7c00dc2426b9fdc8d6202596f9f31391d2134e8797c2c05e83e`；current.activationGeneration=52，previous保留2026.10.21-ble3。正式SNI/TLS GET下载复验版本、长度和哈希均一致，匿名401。未串口刷入本次固件，未声称用户实板升级/重启回报通过。

独立代码复核未发现剩余阻断；真实手机直连输入、现场收音、OTA下载安装与开机回报仍由用户稍后验收。
