# Authorized App OTA Implementation Plan

Goal: automatic private firmware download and reboot verification in App.
Architecture: cloud single-use challenge + BLE HMAC proof + scoped ephemeral download capability. Read-only INFO reports running firmware and boot state.
Tech: Python stdlib, IDF6 PSA, NimBLE, Flutter HTTP/BLE.

- [ ] Add failing tests for authorization expiry/replay/device scope, immutable download and HTTP routing. Implement display_service/app_ota.py and early isolated app-OTA handlers in app.py. Run Python regressions.
- [ ] Add INFO/AUTH characteristics to firmware-epaper/main/ble_ota.c using device_config.h and PSA HMAC. No existing transfer opcodes changed. Build official IDF via Actions.
- [ ] Add testable App download client and boot identity parser/poller, tests before implementation. Integrate FirmwareScreen and BleOtaService; validate metadata/hash before BEGIN; show actual reboot verification in PushScreen.
- [ ] Run analyze/tests/signed APK build via Actions; stage firmware privately. Back up live server and deploy only App OTA module/handler changes; validate authenticated public download and denied replay.
- [ ] Install bootstrap board firmware only when hardware connected. Exercise real BLE download/transmit/restart/readback; retain evidence. Provide signed App through existing store publication workflow. Mark physical phone App test pending if unavailable.
