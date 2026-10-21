# 本项目工作约定

用户已指定后续开发、修复在云端完成，固件走云端构建和OTA。默认编辑与测试位置为106服务器 `/opt/phone-controller-workspace`；Mac副本用于同步和用户明确需要的硬件诊断。具体要求遵循 `.cursor/rules/cloud-workflow.mdc`，部署流程见 `docs/cloud-development-and-ota.md`。

手机允许用户手动开启ADB5555，不装手机控制App、不开Wi-Fi；用户已明确允许安装并启用ADB Keyboard用于中文输入，每次输入结束/失败/停止后恢复原输入法并保留结果页；本轮暂不改USB Host硬件。仅操作明确授权的目标设备，模拟执行与真实手机直连验收分别报告。不得公开令牌、私钥或含设备身份的固件。
