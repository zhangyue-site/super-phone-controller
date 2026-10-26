# Cloud text task relay (candidate)

云端服务 owns planning and dispatch; the phone forwards signed BLE08 packets; ESP32 emits USB HID. Codex and a desktop are not runtime components. The phone never receives the device key. A short-lived BLE possession capability gates the transport. Delivered actions are persisted before returning and never replayed; missing receipts require reconciliation. Enable EPAPER_RELAY_CONTROL=1 only after private service configuration and integration verification.

This candidate retains existing modules from the development workspace. Unit and integration results do not prove a successful phone task. Alipay→Achai single save/readback, phone background lifecycle and the simplified task/device UI remain unverified. No bulk accounting is enabled by this transport. Existing target-app restrictions remain. Voice is deferred.

Build Android using the existing GitHub Actions workflow on this branch. Release signing uses repository Secrets; keys and private observations are excluded from source. Do not package development logs or personal bill screenshots. Keep the installed APK for rollback, and verify signing certificate before updating.
