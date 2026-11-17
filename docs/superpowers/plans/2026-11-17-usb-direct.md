# USB Direct Implementation Plan
Goal: remove mandatory BLE from USB-connected target startup without bypassing authorization.
Architecture: existing PCUSB proof bridge + independent server challenge scope; reuse existing controller pairing and lifecycle.
Tech Stack: Flutter/Dart, Android native bridge, Python HTTP.
- [ ] Backend: failing offline proof/HTTP tests; implement usb-challenge/authorize/renew with isolated nonce authority, exact fields, replay/serial/device/expiry checks. Keep pairings attached to stable renewed ticket.
- [ ] App: failing ControlClient native-channel/HTTP tests, add authorizeUsb and renew via USB info/sign with current-session checks, cleanup on cancellation; retain USB client without a BLE service.
- [ ] Target startup: USB default, optional BLE relay button, no automatic BLE scan or Bluetooth-on gate; preserve capture/STOP/USB mode windows and generation fencing.
- [ ] Review behavior and code; run backend/auth/lifecycle regressions, Flutter tests/analyze. Add workflow regressions for new USB auth tests.
- [ ] Commit/push release branch; Android build through existing GitHub Actions with incremented code/version. Verify signed/encrypted artifacts and deploy compatible backend using backup/hash/rollback process. Physical acceptance remains separately recorded.
