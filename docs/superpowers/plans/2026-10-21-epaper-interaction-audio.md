# Epaper Interaction and Audio Implementation Plan

> Execute inline using executing-plans. User requested direct implementation and testing.

**Goal:** Improve the 200×200 board UI, add real speech prompts and persistent output volume/mute, and fix BLE updater lifecycle.
**Architecture:** Keep existing firmware page IDs and consent checks. Pure UI/audio policy headers drive host tests. Voice worker owns codec for recording/playback serialization. Generated screen/PCM assets are committed and reproducible. Flutter owns scan/connection/update state per route.
**Tech Stack:** ESP-IDF, esp_codec_dev ES8311, Pillow, host C++, Flutter/Dart.

- [x] Add failing host regressions for symmetric page navigation, fixed stop/home, sound controls, recording release and invalid touch gesture samples.
- [x] Implement page/input policy, dynamic status and sound screens; update generator and inspect PNGs.
- [x] Verify Waveshare V2 audio pins, implement shared codec output and persistent volume/mute; embed bounded offline Chinese prompts and cancel playback before recording.
- [x] Fix Flutter scan/navigation, connection gating, firmware validation and cancellable update status lifecycle; add meaningful tests.
- [x] Run host/Python/Flutter tests and firmware build, inspect artifacts, review diff; record limits and hardware acceptance steps.

Verification record: docs/handoff/2026-10-21-interaction-audio-validation.md. Native Android packaging and physical-board validation are reported separately from host tests.

## 最终交互更新

用户最终选择屏幕与语音。屏幕单击开始连续输入、自动静音分句、识别播报后继续听；大区域停止，离开语音页取消；10 秒无声退出，最多 12 轮。现有实体键仅兼容。实际能力为 ASR 与提示，聊天回答和手机执行器尚未接入。
