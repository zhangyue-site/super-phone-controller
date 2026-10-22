# USB Auto Screen Implementation Plan

**Goal:** Insert existing S3, launch the existing Android helper and request full-screen consent after board authorization.
**Architecture:** Android validates USB attachment and sessions; Dart binds the explicitly selected BLE board and coordinates a single consent attempt. Existing screen service owns frame upload and revocation.
**Tech Stack:** Kotlin Android USB/MediaProjection, Flutter MethodChannel/BLE, Python contract tests.

- [x] Add failing USB launch/late-grant Dart tests and USB descriptor/manifest contract test; run red.
- [x] Implement Android UsbLaunchBridge lifecycle, bounded physical detach handling, local USB/BLE bindings, native consent/session guards; do not claim USB interfaces.
- [x] Implement Dart USB session and launch coordinator; integrate DeviceScreen first pairing/known binding and FirmwareScreen auto-sharing; retain manual fallback.
- [x] Fence ScreenShare authorization and revoke unclaimed grants; test cancellation, stale detach, binding mismatch and duplicate consent.
- [x] Run analysis, 29 Flutter tests and 140 Python tests; cloud-native signed build completed on source c6cbe98; independent final Actions run 39761662276 succeeded.
- [x] Audit actual APK, original cert/icons, immutable publish/store merge, full public download and handoff package. Physical acceptance is recorded separately as pending.

Design review approved after clarifying first user pairing (logical BLE ID differs from USB MAC). Cloud analyze passed, 29 Flutter tests and 140 Python tests passed. DeepSeek reviewed selected code and found no blocking issue; actual USB/default-app/MediaProjection behavior remains a physical acceptance item.
