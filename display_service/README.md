# 手机控制协调服务

该目录是可配置的服务端源码，不包含维护者的生产部署、账号、模型凭据或真实设备配置。默认只监听本机回环地址；对外部署需要自行提供 TLS、认证配置、存储目录和网络策略。

运行入口为 `python3 -m display_service.app`。当前分支的功能与实机验收状态以仓库首页为准，不能把接口返回成功等同于手机操作已经通过画面核验。

## 配置

配置文件由部署者放在仓库外。不要把设备令牌、模型 API key、Cookie、签名材料、私人画面或运行日志提交到 Git。

| 环境变量 | 用途 | 未提供时 |
| --- | --- | --- |
| `EPAPER_CONFIG` | 设备 ID 到设备令牌的外部 JSON 映射 | 使用通用 `/etc/phone-controller/devices.example.json` 路径，不内置设备 |
| `EPAPER_MODEL_CONFIG` | 模型路由 JSON，结构为 `models.providers` | 当前用户 `.config/phone-controller/models.json`；无配置则不能调用模型 |
| `EPAPER_JEV_CREDENTIAL` | 可选的图像判断提供方凭据 | 当前用户 `.config/phone-controller/jev.json`；不包含默认账号 |
| `EPAPER_JEV_PROXY` | 可选的图像判断代理 | 默认直连，不连接隐藏的本机代理 |
| `EPAPER_SPEECH_CONFIG` | 可选的语音合成配置 | 当前用户 `.config/phone-controller/speech.json`；不包含默认账号 |
| `EPAPER_ASR` | 部署者配置的识别适配脚本 | 明确报未配置，不回落到维护者服务器路径 |
| `EPAPER_ASR_CHECK_WAV` | 开发者自有的语音探测样本 | 相对路径 `assets/asr-check.wav`，不包含私人录音 |
| `EPAPER_QUOTAS` | 可选的额度摘要输入目录 | 当前用户 `.local/state/phone-controller/quotas` |

没有配置凭据、模型、设备或语音适配器时，相应功能保持不可用；不会自动使用个人部署。生产配置需自行根据所选服务填写并保存在仓库之外。

## 接口与验证

设备读取状态和 200×200 位图的接口包括 `/status`、`/screen.bin`、`/screen.png`。画面上传、手机任务与蓝牙中继分别使用 `/app-screen/`、`/app-control/`、`/app-relay/` 下的受限接口；具体请求与安全边界见源码和对应测试。不同用途的短期票据不应混用。

真实控制验收需要同时核对：目标身份、用户授权的新画面、同一任务的派发与板端回执、动作后的独立画面结果。模拟数据和单元测试仅证明各自覆盖的逻辑。

`deploy/` 仅保留通用示例，不是维护者的实际服务器配置。历史专属额度采集适配器和旧私有服务器入口已从公开源码移除；可选额度展示仍可读取部署者自行提供的摘要数据。
