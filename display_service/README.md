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
| `EPAPER_SPEECH_CONFIG` | 独立的 MiMo Token Plan 语音配置 | 必须显式提供；只接受代码列出的订阅地址，不回退按量端点 |
| `EPAPER_ASR` | 部署者配置的识别适配脚本 | 明确报未配置，不回落到维护者服务器路径 |
| `EPAPER_ASR_CHECK_WAV` | 开发者自有的语音探测样本 | 相对路径 `assets/asr-check.wav`，不包含私人录音 |
| `EPAPER_QUOTAS` | 可选的额度摘要输入目录 | 当前用户 `.local/state/phone-controller/quotas` |

没有配置凭据、模型、设备或语音适配器时，相应功能保持不可用；不会自动使用个人部署。生产配置需自行根据所选服务填写并保存在仓库之外。

## 接口与验证

设备读取状态和 200×200 位图的接口包括 `/status`、`/screen.bin`、`/screen.png`。画面上传、手机任务与蓝牙中继分别使用 `/app-screen/`、`/app-control/`、`/app-relay/` 下的受限接口；具体请求与安全边界见源码和对应测试。不同用途的短期票据不应混用。

真实控制验收需要同时核对：目标身份、用户授权的新画面、同一任务的派发与板端回执、动作后的独立画面结果。模拟数据和单元测试仅证明各自覆盖的逻辑。

`deploy/` 仅保留通用示例，不是维护者的实际服务器配置。历史专属额度采集适配器和旧私有服务器入口已从公开源码移除；可选额度展示仍可读取部署者自行提供的摘要数据。

## 当前执行与回归契约

生产导航使用 USB HID 和用户主动共享的新画面。中文搜索先输入拼音，再依据真实候选栏选择目标前缀，最后核验已提交的原文；保留手机现有输入法。安装 `requirements-keyboard.txt` 中固定版本的依赖。历史 `type_text` 记录仍可读取和校验，但不是生产输入兜底。

手机视觉的 `opencode-go` 请求固定到官方 Go `/inference/go/openai/v1` 地址，直连且禁止重定向。模块变量 `EPAPER_PHONE_VISION_GO_BASE_URL` 只能填写同一官方地址，不能启用其他渠道。传输超时、网络错误、429 和 5xx 最多在更新后的画面上重试一次；授权、格式和语义错误不重试，已经收到板端 ACK 的动作不重放。模型自报 confidence 仅为诊断信息，不能授予执行许可；仍需通过语义、结构、坐标、会话和动作前新画面检查。

蓝牙 Gateway 和直连设备领取共享单一执行所有权；待领取任务在确认后 60 秒过期，执行中任务使用独立的生命周期限制。STOP、掉线、过期或回执不明不会将旧动作转交给另一个入口。`board_control.py` 保留历史会话工具及元数据兼容逻辑，当前 HTTP Handler 未注册 `/board-control`；手动指令和技能仍通过已认证的 App/配对入口及同一执行链路处理。

完整离线回归可运行 `python3 tools/run_offline_tests.py --include-focused`。此入口禁止 Python 外部 socket 连接，只允许本机 HTTP 测试；模型响应和手机画面均使用合成 fixture，不代表实机验收。
