# Open-AutoGLM 接入进度

上游固定版本86f55382982fb054e8fc98ca80609dff8a2cdc3c，使用官方ModelClient、中文提示词及动作协议解析。独立运行环境/opt/phone-controller-autoglm-venv，不修改其他服务SDK。现有可用视觉模型mimo-v2.6-flash，连接探针已成功；没有部署AutoGLM-Phone-9B权重。

106服务端规划，板端邮箱执行；新增截图与受控中文输入命令。输入仅允许聚焦搜索框和用户原话子串，动作前复核完整当前UI，完成后需要联系人标题和独立姓名节点，拒绝无结果提示。截图编码上限768KB、ACK正文850KB；PSRAM缓冲及超时同步扩展。

IME正常输入后立即恢复；失败/可捕获中断用trap恢复，断连遗留恢复标记，下次ADB连接先恢复，恢复前阻止新任务。断线当下不能保证立刻恢复，应如实提示待重连恢复。

17项固件主机测试、85项Python测试通过。审查发现并修复expire缩进和“未找到”误报成功问题。小米实测：微信搜索框已写入李洋，结果包含联系人标题及独立李洋节点，默认IME恢复豆包，结果页保留。这是Mac诊断调用，与板端语音验收分开。首次无等待时文字未写入；按官方切换/清空/输入/恢复等待后成功，固件已修正。

完整云端规划器桥接测试因手机前台从豆包变化到饿了么而停止，没有重放动作，已请求用户暂停操作和其他自动化任务。ci57云端构建中；服务端代码已部署但EPAPER_PHONE_BACKEND=legacy，待新固件升级再启用autoglm。原服务代码备份/var/backups/phone-controller/before-autoglm-20261021.tar.gz，运行环境drop-in /etc/systemd/system/phone-controller-display.service.d/10-autoglm-runtime.conf。
