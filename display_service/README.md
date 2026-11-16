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

## 通用任务 Agent 源码

通用执行器以正常Python模块发布，不依赖维护者的版本后缀、生产manifest或服务目录。显式设置 `EPAPER_PHONE_AGENT=1` 时，已认证远程任务经 `Conversation.start_remote` → `agent_loader.run` → `agent_integration.run` 进入执行器；默认仍不开启。模型输出、OCR及稳定性报告都是不可信观察，不能授予控制权限。每个输入仍绑定原任务、设备、会话和新画面，写入结果不明时停止，不自动重放。

额外配置：`EPAPER_STATE` 指定通用Agent状态目录（默认相对 `state`）；`EPAPER_MODEL_CONFIG` 指向部署者私有的模型配置（须和已有模型路由配置一致）；可选 `EPAPER_OCR_URL`、`EPAPER_OCR_TOKEN_FILE` 明确配置辅助OCR，未配置不会连接维护者服务。可选工作台OCR诊断仅对 `EPAPER_WORKBENCH_OCR_DEVICES` 显式登记的设备开放，默认空；它不改变执行许可。私有账号、设备和状态数据均不在源码中。

`local_observation`同时要求手机端ready=true、达到该报告的requiredFrames（4或10）且稳定时长至少600ms；不能把native 10帧改判为4帧就绪。无效手势容器只触发有界重新观察/规划，不裁剪扩大坐标、不放宽写入限制、不重放输入。

`tests/test_agent_public_chain.py` 用合成手机和打桩的规划器，经真实HTTP处理器完整驱动上述入口链路（领取→理解→观察→本地稳定性请求→HID→新帧核验），由 `tools/run_offline_tests.py` 一并运行，用于定位任务停在哪一环。合成条件下服务端各环节可以闭环；手机若不能为请求区域提供连续新源帧，任务以 `observation_pipeline_blocked` 停止且不发送输入，回复附带最近一轮观察到的原因（仅计数，不含画面文字）。等不到新帧时按手机最近上报的亮屏/锁屏状态说明原因，不再一律提示重新共享。该测试不代表真机、模型或控制板验收。

Agent状态目录不存在时会自动创建。`tools/run_offline_tests.py` 在未设置 `EPAPER_PAIRING_STATE` 时使用临时配对库，不触碰部署路径。

运行 `python3 tools/run_agent_offline_tests.py` 验证合成Agent回归；运行 `python3 tools/run_offline_tests.py` 验证现有公开契约。需要仓库现有Pillow和 `requirements-keyboard.txt` 依赖。测试禁止外网，不能证明真机动作成功。

此次导出不含维护者专用账单单步派发、临时OTA设备闸门、私有模型配置、运行状态或未接线的native local-loop草稿；保留公开版既有严格nonce/重放规则，未混入其他部署的中继接管策略。线上版本与公开通用代码的这些差异是明确保留的部署边界，不能声称整套生产环境已原样复制或真机全部验收完成。
