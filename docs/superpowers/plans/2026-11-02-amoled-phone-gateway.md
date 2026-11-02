# AMOLED phone gateway implementation plan

Goal: phone-mediated cloud access and protected BLE update for AMOLED without changing the live device.
Architecture: reuse the existing phone cloud relay; add a target-local OTA engine and BLE adapter; validate target family end to end.

- [x] Add failing host tests for OTA lifecycle, cancellation, authentication and flash integrity.
- [x] Implement portable OTA state machine with platform adapter and image-bound HMAC v2 grant.
- [x] Integrate GATT, OTA/input exclusion, disconnect and local STOP.
- [x] Add failing Flutter tests for connected target, 6 MiB slot and semantic version fences; implement.
- [x] Update target-aware server validation and tests using private registry configuration.
- [x] Run host, Flutter, privacy and firmware cloud build checks; document exact acceptance boundary.
- [x] Record phone model deployment as a separate follow-up, without publishing private model/data or claiming device latency.

Final firmware and signed Android cloud builds both passed; physical installation and phone acceptance require a separate authorized hardware window. See docs/amoled/STATUS.md.
