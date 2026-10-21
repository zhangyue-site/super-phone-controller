# 本项目工作约定

用户已指定后续开发、修复在云端完成，固件走云端构建和OTA。默认编辑与测试位置为云端服务服务器 `/srv/phone-controller/workspace`；Mac副本用于同步和用户明确需要的硬件诊断。具体要求遵循 `.cursor/rules/cloud-workflow.mdc`，部署流程见 `docs/cloud-development-and-ota.md`。

手机允许用户手动开启ADB5555，不装App、不开Wi-Fi；本轮暂不改USB Host硬件。仅操作明确授权的目标设备，模拟执行与真实手机直连验收分别报告。不得公开令牌、私钥或含设备身份的固件。
