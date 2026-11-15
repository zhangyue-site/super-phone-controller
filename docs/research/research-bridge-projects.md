# 同类"ESP32/手机控制桥"开源项目调研报告

调研时间：2026-11-15 · 方式：GitHub 搜索 + 官方文档/README 实读
我方参照：ESP32-S3 USB-OTG HID + Flutter App(pcflash) 投屏 → 云端 OCR/决策 → 板子 HID 执行。
已知痛点：①板子长时间无连接死机需断电；②页面确认反复 nav exhaust；③驱动空转需重启；④App 断链不自愈。

---

## 一、逐项目对比

### 1. shenlan-ai/esp32-android-agent（36★）—— 与我们架构几乎同款，闭环质量最高
- 核心思路：PC 端 FastAPI 工作台 + ESP32 BLE/S3 USB HID 输入 + ADB 截屏，视觉模型 plan→observe→validate→serialize→verify。
- 比我们强的地方：
  - **每个动作独立验证**：动作执行后截屏比对，"模型声称完成"不算数，还要做一次独立的"全目标复核"（independent full-goal check）。
  - **动作/时间/Token 三重预算**：每步有 budget，超了就停，不空转——直接治我们的"驱动空转"。
  - **失联即暂停，绝不静默降级**：截屏丢失或连接断开 → 任务自动 pause 等人接管；"HID 失败永远不悄悄切 ADB 输入"。我们 App 断链不自愈正是因为没有这种显式状态机。
  - 不确定时"先观察再恢复"，不盲注输入。
- 可借鉴：
  1. 每动作后强制截屏校验 + 目标级二次确认；
  2. nav exhaust 应触发"暂停并上报"而非无限重试；
  3. 断链状态机：DEGRADED/PAUSED 状态显式上报云端，恢复后人工或规则确认再续跑。

### 2. firerpa/lamda（8.7k★）—— 设备侧常驻 agent + 群控工程化标杆
- 核心思路：服务直接跑在安卓设备上，160+ API、WebRTC/H.264 远程桌面、UI Watcher、MCP/Agent，专为多设备 7×24 无人值守设计（StarLink Hub 集群）。
- 比我们强的地方：
  - **UI Watcher 机制**：监听 UI 变化，条件命中自动执行点击/按键——"弹窗/升级提示/广告"类打断被 watcher 兜底消化，主流程永远不会因为一个意外弹窗卡死（nav exhaust 的常见根因）。
  - **云端 OCR 集中化**：集群里识别跑在云端 GPU 而非端侧，弱端也能用。
  - 长稳工程化：frida 脚本崩溃后自动重注入（等价于"驱动空转自动重启"做到进程级）、统一配置、Docker 化部署。
- 可借鉴：
  1. 给我们手机端 App 加"UI Watcher"层：常见打断页（权限弹窗/更新弹窗）白名单自动关掉，再进决策主循环；
  2. 云端决策输出结构化 selector（text/resourceId）而非纯坐标，减少误确认；
  3. 驱动空转 → watcher 超时自动重启该模块，粒度到模块而非整机断电。

### 3. openatx/atxserver2（1.4k★）+ DeviceFarmer/stf（~9k★）—— 设备掉线自愈的教科书
- 核心思路：Provider(每台宿主机一个) 通过 adbkit 监听 USB 插拔 + 维持 websocket 心跳，Server 只信任心跳。
- 比我们强的地方：
  - **心跳即真相**：provider 每 10s 向 server 发心跳，server 侧超时（如 30s 无心跳）直接把设备标记 offline，任务释放回队列，**不**在旧连接上死等。
  - **状态机单向流转**：online→busy→offline→online，每次转换有事件日志；任务只发给 online 空闲设备，offline 设备上的任务自动重排。
  - 设备重插上电后 provider 重新发现（adb track-devices 事件驱动）→ 自动重新注册 → 恢复 online，全程无人工。
- 可借鉴：
  1. 板子/App 与云端之间加双向心跳（≤10s 周期，3 次超时判死），判死后云端主动放弃旧会话、任务重排；
  2. 恢复用"事件驱动重注册"（USB 连接/网络恢复事件触发 hello），而非轮询猜测；
  3. 所有状态变更落事件日志，方便排查"死机前发生了什么"。

### 4. SonicCloudOrg/sonic（server 2.2k★ / agent 1.7k★）—— 云真机平台的连接治理
- 核心思路：Java Agent 通过 Netty websocket 长连接回传屏幕流，server 侧 idle-state-handler 检测半开连接。
- 比我们强的地方：
  - **半开连接检测**：Netty IdleStateHandler，N 秒没读写就主动断，靠重连握手重建会话——专治"App 显示在线实际已死"。
  - agent 端 adb 设备监听独立于屏幕流通道：控制通道断了，设备枚举通道还在，重连后能秒级恢复画面。
  - 屏幕流有分辨率/码率自适应，弱网降帧不断流。
- 可借鉴：
  1. Flutter 端 websocket 加 idle 超时 + 指数退避重连 + 会话 token 重入（rejoin 而非重新登录）；
  2. 心跳/控制/媒体三条通道分离，弱通道只降级不整体断；
  3. 投屏帧自适应降分辨率，优先保住控制通道的实时性。

### 5. X-PLUG/MobileAgent（9.4k★）—— "截屏→决策→注入"反思回路最强
- 核心思路：Mobile-Agent-v2/v3 三智能体（决策/反思/操作），每步操作后截屏交给反思 agent 检查"操作是否生效、是否偏离目标"，失效则回退重试。
- 比我们强的地方：
  - **操作前/后双截屏 diff 验证**：点击后画面没变化 → 判定无效 → 换策略（换 selector/滚动/返回），有次数上限，超限上报。
  - v3 加了**进度感知（progress awareness）**：长任务里记录已完成子目标，卡住时判断"是新页面还是原地打转"，原地打转立即止损。
  - 屏幕理解用结构化（XML 树/OCR + 布局），不是裸像素，页面确认准确率高得多。
- 可借鉴：
  1. 我们云端决策加"点击前后截屏比对"，无效点击计数，2 次无效就换导航策略而不是重复同一点击；
  2. 进度感知：连续 N 步截图相似度高 → 判定空转 → 触发恢复动作（back/home/重开 App）；
  3. nav exhaust 的正确行为是"回到已知安全点（home/入口页）重规划"，不是反复确认。

### 6. mobile-next/mobile-mcp（10.6k★）—— 用 accessibility 树代替像素级确认
- 核心思路：MCP 服务器暴露真机/模拟器控制给 AI agent，优先用 UI 自动化树（accessibility/XML）定位元素，截屏只做辅助验证。
- 比我们强：元素级定位天然抗分辨率/主题变化，"页面确认"变成查树而非 OCR 匹配。
- 可借鉴：手机端 App 若能读到无障碍树或当前 Activity 名，随投屏帧一起上传，云端确认成本骤降。

### 7. qinghemuyu/QineTouch（51★）—— ESP32-S3 USB HID 触控注入的工程实践
- 核心思路：PC 端 Go sender 监听键鼠 → 串口/WebSerial 发指令 → ESP32-S3 USB HID 输出多点触控（专用触控描述符而非鼠标），专攻投屏游戏宏。
- 比我们强：**用 HID 触控协议（digitizer）而非 mouse 报文**做点击，安卓按原生的多点触控接受，兼容性好；指令带序列号可对账。
- 可借鉴：若目标 App 对鼠标 hover 敏感，改用触控 digitizer 描述符；指令加 seq/id 回执，驱动才能知道哪条没送达。

### 8. ESP32 固件死机防护通用做法（Espressif 官方文档 + 社区实践）
针对"长时间无连接死机需断电"：
  1. **TWDT 任务看门狗**：`esp_task_wdt_init(config)` + 每个关键任务 `esp_task_wdt_add()` / 周期 `esp_task_wdt_reset()`；尤其给 TinyUSB 的 tud_task 和 Wi-Fi 任务加订阅。menuconfig 开 `CONFIG_ESP_TASK_WDT_PANIC=y` 让超时直接 panic 复位（默认只打印不复位！这是大多数"死机"的根因）。IWDT 中断看门狗默认开，确认 `CONFIG_ESP_INT_WDT_TIMEOUT_MS` 合理。
  2. **USB 掉线恢复**：主机停止轮询/挂起时 `tud_ready()`/`tud_mounted()` 会变假；发送 HID report 必须带超时和重试，禁止在 `tud_task` 里阻塞等 host。连接丢失后用 `tud_disconnect()/tud_connect()` 强制重新枚举；连续 M 次枚举失败 → `esp_restart()`（软件复位等效断电重启，不用断电）。
  3. **OTA A/B 回滚**：开 `CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE`，新版固件需显式 `esp_ota_mark_app_valid_cancel_rollback()` 确认；板子反复崩溃时 bootloader 自动回滚到上一个可用固件——不再需要人工断电刷机。
  4. **复位原因自诊**：启动时读 `esp_reset_reason()`，若是 TWDT/panic 复位，通过 RTC 慢速内存或 NVS 记录崩溃上下文并上报云端，形成"死机画像"。
  5. Wi-Fi 侧：禁用 modem power save 或加大 keepalive，配合 `esp_wifi_set_ps(WIFI_PS_NONE)` 排除"无连接时省电逻辑挂死"这一常见元凶。

---

## 二、我们值得抄的前 5 名做法（按投入产出排序）

1. **双向心跳 + 3 次超时判死 + 任务重排**（学 atxserver2/STF/Sonic）
   板子与 App 各自 ≤10s 心跳；云端 30s 无心跳标记 OFFLINE 并放弃会话；恢复时事件驱动重注册。这一条同时治：死机发现太慢、App 断链不自愈、云端给死设备派任务。
2. **TWDT 全覆盖 + CONFIG_ESP_TASK_WDT_PANIC=y + 连续 USB 枚举失败 esp_restart()**（学 Espressif 官方实践）
   给 tud_task/Wi-Fi/主控任务都 `esp_task_wdt_add`；USB 用 tud_ready() 带超时发送 + tud_disconnect/connect 重枚举；连续失败软复位。"断电重启"降级为"秒级软复位"。
3. **点击后截屏 diff 验证 + 无效点击换策略**（学 MobileAgent 反思回路）
   每次注入后截屏比对；同一点连续 2 次无效 → 换定位方式或触发恢复动作（back/home）；nav exhaust 改为"回安全点重规划 + 上报"，严禁无限重试。
4. **动作/时间预算 + 失联即 PAUSE**（学 esp32-android-agent）
   每步设超时与重试上限，超限即停并上报；任何通道断开 → 任务置 PAUSED（不是继续跑也不是静默降级），恢复后由云端规则确认续跑。
5. **UI Watcher 兜底打断页 + 结构化页面确认**（学 lamda / mobile-mcp）
   手机端维护常见弹窗白名单（权限/更新/广告），命中自动关闭后再进主流程；投屏帧附带当前 Activity/无障碍树信息，云端确认用结构化字段而非纯 OCR，页面确认失败率大幅下降。

---
附：关键参考
- https://github.com/shenlan-ai/esp32-android-agent （动作预算/失联暂停/独立复核）
- https://github.com/firerpa/lamda （UI Watcher/集群工程化）
- https://github.com/openatx/atxserver2 、https://github.com/DeviceFarmer/stf （心跳即真相/状态机）
- https://github.com/SonicCloudOrg/sonic-server （Netty idle 检测半开连接）
- https://github.com/X-PLUG/MobileAgent （前后截屏 diff/进度感知）
- https://github.com/mobile-next/mobile-mcp （accessibility 树定位）
- https://github.com/qinghemuyu/QineTouch （S3 HID 触控描述符）
- https://docs.espressif.com/projects/esp-idf/zh_CN/latest/esp32s3/api-reference/system/wdts.html （TWDT/IWDT/四阶段超时）
