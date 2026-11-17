# 借鉴 NanoKVM 的设备诊断改进

## 范围与状态
基于云端源码基线 5ffbf2d，独立候选，不覆盖其他开发。未部署在线服务，未刷机，未控制真实手机。
NanoKVM 借鉴点：设备能力分项呈现、统一 AI 接入前的状态观察。首轮实现服务端诊断，MCP 和 APP 界面留待后续。

## 接口
沿用 POST /app-control/command 和现有 Bearer 控制票据。
请求仅允许 {"operation":"diagnostics"}，拒绝 text、task_id、device。目标由授权身份推导，过期或撤销返回 403。
诊断不调用任务同步、不保存任务、不领取、不取消、不产生手机输入。授权的自然到期清理仍由既有授权模块处理。

## 字段含义
- controlAuthorized：本次查询通过现有控制身份验证。
- screenAuthorized：采样时有有效的屏幕共享授权；不能证明手机亮屏或正在上传。
- heartbeat：state=fresh/stale/unknown，code 仅 fresh 时返回；ageSeconds 为服务端收到事件以来秒数，未知 null。
- reportedReady / pointerCompatible：通过有效 lease 与序号屏障的近期 claim 报告，45 秒后 null；不证明物理许可现在仍有效。
- taskBusy / voiceBusy / taskQueued：独立占用状态；查询不修改过期队列。
- frameAgeSeconds / frameFresh：仅当前有效捕获来源且图像数据存在时计算，使用 mailbox 时钟；10 秒是诊断展示阈值，不改变原有导航帧门限。
- inputReady：存在已知阻塞或缺少必要遥测时 false；未发现这些问题时仍为 null。正向遥测不等同真实物理许可。
- reasons：可机器识别的观察原因；advisory 固定 true。所有字段只是非原子采样，执行时仍经过既有授权与动作检查。

## 心跳
读取最近 512 条服务器事件，同一最近观察 boot 选最大 seq 的 exec，45 秒内有效。未来时间、缺少时间戳、非法 code 不作为可执行证据。
新 boot 无 exec 时不借用旧 boot 的 ready。大量 UI 事件不受仅 100 条展示 tail 限制。
这是接收新鲜度，缓冲或乱序上报不能证明实际设备当前状态。

## claim 增量兼容
原有 op、lease 和任务编号不变。wait 增加 reason：
lease_required、retired_session、sequence_rejected、voice_busy、device_not_ready、pointer_protocol_mismatch、device_busy、screen_not_authorized、no_queued_task。
保持原有序号消费次序、私聊共享建立流程和 Android 必须已有共享授权的条件，不重放任何动作。

## 验证
测试使用合成事件、假 HID 与隔离 HTTP；未调用真实视觉模型，不把模拟测试视为真机成功。
覆盖鉴权、严格字段、撤销、来源绑定、任务无副作用、旧心跳、重启、空帧、语音占用以及现有停止/配对/共享回归。
