# Agent 任务停住时收集哪些日志

本文说明通用 Agent（`EPAPER_PHONE_AGENT=1`）任务停住后，服务端和手机端各有哪些现成的诊断记录、到哪里取、每个字段是什么意思。目的是让排查的人或 AI 拿到同一份事实，而不是靠描述猜。

这些记录只用于定位停在哪一环。它们不授权任何操作，不触发重试，也不代表真机验收。

## 最小收集清单

任务停住后，按顺序收集这五样：

1. **任务回复原文。** 回复里已经写了停在哪一步，见下方“回复与环节对照”。
2. **服务端结果文件** `agent-runs/<任务号>-result.json`。
3. **服务端标准输出里这次任务时间段的日志行**，至少包含 `LOCAL_STABILITY_PENDING`、`FRAME_WAIT_TIMEOUT`、`AGENT_DOCTOR`。
4. **手机端脱敏诊断。** 在被控手机上打开“设置与设备维护”→“连接诊断与兼容说明”→“复制脱敏诊断”。
5. **APK 的构建参数。** 是否带 `PCFLASH_SOURCE_BURST=1`，版本号是多少。

第 4 项要在任务停住后尽快复制。手机只保留最近 192 条，后续事件会把旧的挤掉。

## 回复与环节对照

| 回复里出现的话 | 停在哪一环 |
| --- | --- |
| 共享授权仍有效，但 N 秒内没有收到新的手机画面 | 手机没有上传新帧。回复会接着说明是锁屏、息屏还是原因未确认 |
| 未收到新的手机画面，请在App中共享整个屏幕 | 这台设备当前没有有效的共享授权 |
| 目标连续3轮未取得10个稳定新源帧 | 画面看到了、点击也规划了，但手机没交出稳定性证明。此时没有发送任何输入 |
| 最近一轮：服务端没有收到新的共享帧 | 等待期间帧上传中断 |
| 最近一轮：手机回报中始终没有本次请求的目标区域 | 稳定性请求没被手机采纳，或回报没带回来 |
| 最近一轮：手机已收到请求，但没有产生新的源帧 | 静止页面上源帧突发没有启动或没有出帧 |
| 最近一轮：相邻源帧间隔超过250毫秒 | 源帧来得太慢，连续计数被重置 |
| 最近一轮：目标区域像素在变化 | 目标区域本身在动，例如动画、光标或视频 |

“最近一轮”后面的原因是服务端根据收到的帧推出来的。服务端只能看到上传成功的那部分帧，所以它是线索，不是结论。要确认，看手机端的 `local_stability` 记录。

## 服务端

### 标准输出

服务把结构化日志打在标准输出，每行以固定标签开头，后面是一段 JSON。日志落在哪里取决于部署方式。

| 标签 | 什么时候打 | 内容 |
| --- | --- | --- |
| `APP_SCREEN frame` | 第 1 帧和之后每 10 帧 | 设备、轮次、帧序号、尺寸 |
| `APP_SCREEN_REJECT` | 帧或状态请求被拒 | 错误类型和代码位置，不含请求内容 |
| `FRAME_WAIT_TIMEOUT` | 等新帧超时 | 最新帧序号和年龄、共享是否有效、手机上报的亮屏和锁屏状态 |
| `AGENT_OBSERVATION_MODE` | 每次观察 | 用图像加文字还是只用文字，文字行数 |
| `AGENT_DECISION` | 每次规划 | 下一步动作和依据 |
| `LOCAL_STABILITY_READY` | 稳定性证明达成 | 目标、等待毫秒数、源帧序号 |
| `LOCAL_STABILITY_PENDING` | 一轮稳定性等待失败 | 见下 |
| `AGENT_REPLAN` | 一步失败后重新规划 | 失败码和环节 |
| `AGENT_DOCTOR` | 链路诊断归类 | 任务号、环节、分类码、恢复方式 |
| `AGENT_FINAL_CHECK` | 任务结束前核验 | 是否完成和依据 |
| `RELAY_HTTP_TIMING` | Agent 运行期间的板端请求 | 操作名和耗时 |

`LOCAL_STABILITY_PENDING` 的字段：

- `reason`：`stability_budget_exhausted`（8 秒内没达成）、`no_new_transport_frame`（没有新帧）、`task_scope_changed`（共享任务变了）、`geometry_changed`（画面尺寸变了）。
- `request_region_observed`：手机回报里是否出现过本次请求的区域。
- `consecutive_source_gap_observed`：是否看到相邻源帧间隔超过 250 毫秒。
- `transport_snapshot_gap_observed`：两次上传之间跳过了源帧并且间隔超过 250 毫秒。这只说明上传稀疏，不说明手机端计数被重置。
- `target_counter_reset_observed`：连续计数或稳定时长是否回退过。
- `samples`：最近 8 个样本。每个样本有上传帧序号 `frame_sequence`、源帧序号 `sourceSequence`、源帧时间戳 `sourceTimestampNs`、连续计数 `count`、稳定毫秒数 `stableMs`、手机是否报告就绪 `ready_reported`。

### 状态目录

状态目录由 `EPAPER_STATE` 指定，未设置时是相对路径 `state`。

| 文件 | 内容 |
| --- | --- |
| `agent-runs/<任务号>-understanding.json` | 任务理解结果 |
| `agent-runs/<任务号>-result.json` | 最终结果。`failure` 是失败码和环节，`local_stability` 是达成的证明，`local_stability_failures` 是每一轮失败的完整记录，`doctor` 是链路诊断 |
| `agent-runs/<任务号>-current.jpg`、`-current-ocr.json` | 最近一次观察的画面和识别文字 |
| `agent-runs/<任务号>-last.jpg` | 任务结束时的最后一帧 |
| `agent-runs/frames/<任务号>/` | 最近 32 次观察的画面和识别文字 |
| `agent-doctor/<任务号>.json` | 链路诊断报告 |

## 手机端

### 怎么取

被控手机上打开“设置与设备维护”→“连接诊断与兼容说明”，点“复制脱敏诊断”。打开这个对话框时会立即补记一条 `capture_frame_stats`。

每条记录带手机时钟 `wall_ms`、开机后毫秒数 `elapsed_ms` 和递增的 `index`。记录只包含固定的事件名、阶段、原因和数字，不含画面文字、区域坐标、请求编号、凭据或响应正文。不在固定词表里的值会被丢弃。

同样的内容也会写到 logcat，标签是 `PhoneDiag`。读 logcat 需要 ADB，只在明确授权的开发诊断中使用，日常排查用上面的复制按钮。

### `capture_frame_stats`

共享期间约每 10 秒一条。计数从本次共享开始累计。

- `source_callbacks`：系统通知有新画面的次数。
- `source_frames`：实际取到的源帧数。
- `eligible_frames`：通过新鲜度检查、进入上传和稳定性计数的帧数。
- `upload_ok`、`upload_wait`、`upload_error`：服务端返回 200、返回 202（收到但这一帧没被采用）、上传失败的次数。`upload_ms` 是最近一次上传耗时。
- `source_age_ms`、`eligible_age_ms`、`callback_age_ms`：距上一次对应事件多久，-1 表示还没有发生过。
- `sampling_enabled`：“静态页面持续取样”是否打开。
- `demand`：服务端当前是否在要帧。
- `interactive`、`keyguard_locked`：亮屏和锁屏状态。
- `status_errors`、`status_age_ms`、`http_status`：状态轮询的失败次数、距上次成功多久、最近的 HTTP 状态码。

### `source_burst`

静止页面上为了凑够连续源帧而做的源帧突发。只在 APK 用 `PCFLASH_SOURCE_BURST=1` 构建时存在。

| `reason` | 含义 |
| --- | --- |
| `begin` | 突发开始 |
| `restored` | 突发结束，已切回原画面源并收到新帧 |
| `restored_idle` | 突发结束并切回，但切回后 1 秒内没有新帧 |
| `failed` | 突发异常，共享已停止 |
| `burst_already_attempted` | 这个请求已经做过一次突发，不再重做 |
| `burst_unauthorized` | 当前不满足突发条件，例如未亮屏、已锁屏、授权暂停、共享已过期或控制板会话失效 |
| `burst_reader_swap` | 静态取样正在切换画面源，暂不突发 |
| `burst_budget_exhausted` | 本次共享的突发次数已用完 |

`switches` 是切换次数，`acquired_candidates` 是突发期间收到的帧数。后四种原因每个请求最多各记一条。

一个请求只做一次突发，最长 3 秒、最多切换 20 次，而服务端一轮等待是 8 秒。突发结束后请求还在，就会记一条 `burst_already_attempted`。成功的轮次里它也可能出现，要结合同一请求 `request_end` 的 `ready` 看：`ready` 为假时，它意味着突发做完了但没凑够，静止页面上这一轮之后不会再有密集的源帧。

### `local_stability`

记录手机端对服务端稳定性请求的处理。每个请求一条开始、一条结束。只有包含这项改动的 APK 才有这类记录，先确认版本。

| `reason` | 含义 |
| --- | --- |
| `request_begin` | 手机采纳了一个稳定性请求，开始计数。`burst_enabled` 表示这个 APK 是否带源帧突发 |
| `request_end` | 请求结束，带本次计数结果。服务端撤回请求或换成新请求时出现 |
| `watch_cleared` | 请求还在时计数被手机清掉，带截至当时的计数结果。原因是共享任务屏障变了、服务端不再要帧，或取样出错 |
| `status_barrier_mismatch` | 状态轮询里带着请求，但它的任务屏障和手机当前持有的不一致，没有采纳。手机的屏障靠上传帧的回包更新 |
| `request_barrier_mismatch` | 请求自带的屏障和手机的不一致 |
| `request_geometry_mismatch` | 请求的截图尺寸和手机的不一致 |
| `request_frames_mismatch` | 请求的帧门槛不是 10 |
| `request_region_invalid` | 请求的区域编号、标签或坐标不合法 |

后五种是“看到请求但没采纳”，同一个请求同一个原因只记一条。

`request_end` 和 `watch_cleared` 带的数字，都只统计从 `request_begin` 到结束这段时间：

- `observed_frames`：进入稳定性计数的源帧数。
- `rejected_frames`：被计数器拒收的源帧数，原因是作用域不一致、序号或时间戳重复或倒退、缓冲区不合法。
- `gap_resets`：相邻两个源帧间隔超过 250 毫秒的次数。每次都会把连续计数清零。
- `max_gap_ms`：相邻源帧的最大间隔。
- `change_resets`：目标区域像素变化导致连续计数重来的次数。
- `best_count`：目标区域达到过的最高连续帧数，需要 10。
- `best_stable_ms`：目标区域达到过的最长稳定时长，需要 600。
- `ready`：手机端是否达成过稳定性证明。
- `reports_sent`：带着稳定性回报进入上传的帧数。回报附在帧的文字识别结果里，一帧没有识别结果就不会有回报。
- `reports_ready`：其中报告目标区域已就绪的帧数。
- `reports_dropped`：没能带上回报的帧数。原因是从取帧到识别完成超过 2.5 秒、这一帧的计数快照已被更新的 32 帧挤掉，或这一帧属于旧的共享任务。
- `watch_ms`：这个请求在手机上存活了多久。

### 怎么读 `local_stability`

| 看到的情况 | 说明 |
| --- | --- |
| 服务端打了 `LOCAL_STABILITY_PENDING`，手机没有对应的 `request_begin` | 请求没被采纳。找同一时间的 `status_barrier_mismatch` 或 `request_*`。都没有，说明状态轮询没带到请求，看 `capture_frame_stats` 的 `status_errors` |
| `observed_frames` 是 0 或个位数 | 源帧不够。看同一时间的 `source_burst`：没有任何记录且 `burst_enabled` 为假，说明 APK 没带突发；有 `burst_*` 原因则按上表 |
| `gap_resets` 大于 0，`max_gap_ms` 超过 250 | 源帧来得太慢 |
| `change_resets` 大于 0 | 目标区域像素在变 |
| `ready` 为真，`reports_ready` 是 0 | 手机达成了，但没有任何一帧把“已就绪”带出去。看 `reports_dropped` 和 `reports_sent` |
| `reports_ready` 大于 0，服务端这一轮仍然失败 | 回报发出了但没及时到服务端。看 `upload_error`、`upload_ms`，以及服务端样本里的 `ageMs` |
| `observed_frames` 不少，`reports_sent` 是 0 | 帧在计数，但上传的帧都没带回报。看手机端文字识别是否在工作 |
| 结束原因是 `watch_cleared` | 等待中途计数被清。连续多组 `request_begin` 和 `watch_cleared` 说明屏障或要帧状态在反复变 |

## 交给别人或 AI 之前

- 手机端脱敏诊断只有固定词和数字。
- 服务端日志行里有设备标识和任务号。`AGENT_DECISION`、`LOCAL_STABILITY_READY`、`AGENT_FINAL_CHECK` 还带规划目标和依据，这些来自屏幕内容。
- `agent-runs/` 下的画面、识别文字和结果文件包含屏幕内容。

后两类属于私有诊断证据，不进入公开 Git、Issue、日志或 Release。交给外部工具前，按维护者的私有诊断规则处理。

## 这些记录不能说明什么

- 手机端的数字是这台手机这一次的情况，不代表其他机型。
- 记录诊断事件时会写一次本地存储。这发生在请求开始和结束时，不在逐帧路径上，但没有在真机上测过它对帧间隔的影响。
- 代码存在、构建通过、已部署、真机验收分别记录。有了这些日志只是能看清停在哪里，不等于问题已经解决。
