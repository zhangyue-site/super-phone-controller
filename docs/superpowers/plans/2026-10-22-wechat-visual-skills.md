# WeChat Visual Skills Implementation Plan
Goal: simulate end-to-end WeChat navigation and reusable verified skills without ADB mouse/screens.
Architecture: visual policy executor + bounded mailbox actions + gated absolute HID pointer; per-device verified skill store; App whole-display capture/status.
Tech: Python/Pillow, IDF6/TinyUSB, Flutter/MediaProjection.
- [ ] Add failing Python flow/skill tests and C++ pointer sequence tests.
- [ ] Implement vision contract/client and strict WeChat policy runner, fingerprint cache, durable skill store, frame fences/capabilities and logs.
- [ ] Integrate Conversation routing (feature gate); explicit save uses last successful trace only; do not modify unrelated voice fixes.
- [ ] Implement board normalized absolute pointer report, cancellation-aware move/click/drag state machine and strict JSON validator, capability header; compile/test.
- [ ] Update App capture geometry/whole-screen hints, active task + skill status, compatible firmware notice, version1.0.5+6 and preserve icon.
- [ ] Run regressions, true synthetic HTTP/mailbox simulation, real visual-model fixture test; build firmware and signed App on cloud.
- [ ] Review, deploy targeted files with backup; publish App, stage firmware privately (not flash); document model/mock/hardware boundaries.
