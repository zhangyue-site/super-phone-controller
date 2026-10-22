# OpenClaw dual-channel control implementation plan

> Execute in this session; independent firmware and plugin adapters may be delegated after wire contract is fixed.

**Goal:** WeChat and Telegram private commands prepare immutable plans, require same-context explicit confirmation, dispatch once to a locally consenting S3 and report verified results/stop.
**Architecture:** OpenClaw deterministic /phone command adapter uses trusted command context, authenticated loopback bridge endpoints, pending plan state and shared Conversation engine. Board polls /remote/claim when idle and starts its existing dialogue worker with a board-allocated turn. Claim is non-replayable; lost claims fail rather than replay input. One device active task, terminal proof retained for status/save. ADB only existing Chinese typing path.

- [x] Inspect command SDK trusted sender/channel/authorization and private-conversation identity; fail closed for groups/unknown peers.
- [x] Add remote_control.py model and tests: preview has no execution, owner/channel-bound expiring confirmation, dedup, queue conflict, claim exactly once, STOP all phases, correlated terminal status. No synthetic command accepted by deployment test.
- [x] Add authenticated /bridge/phone request API and device /remote/claim heartbeat+claim using session/sequence headers. Do not expose device token through plugin.
- [x] Firmware voice remote idle polling uses existing lifecycle, local HID consent, sequence/session and dialogue_run, remote cancellation is checked synchronously between operations; local STOP still interrupts input immediately. No parallel STOP socket on the existing single-connection proxy. Host regression and official IDF build. No physical flashing by default.
- [x] OpenClaw plugin /phone command supports both openclaw-weixin and telegram, prepare/confirm/status/stop/save. Results addressed only to originating trusted context, no arbitrary destination. Mock both channels including concurrent double-confirm and STOP; no live messages during setup. If proactive delivery not possible retain explicit status and clearly disclose.
- [x] Run HTTP simulation actual adapter->bridge->simulated board->screen/result, failure/STOP/cross-channel cases. Run full regressions. Review precise diffs.
- [x] Backup/deploy bridge and plugin, validate registration without sending messages, build/stage firmware and document real hardware acceptance outstanding.

Acceptance evidence is in docs/handoff-2026-10-22-openclaw-dual.md. Real channel user-context and physical board/phone acceptance remain outstanding; implementation/deployment and simulated tests are complete.
