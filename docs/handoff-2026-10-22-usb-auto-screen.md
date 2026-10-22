# USB automatic screen sharing release — 2026-10-22

Published Android 1.0.8+9, package site.zhangyue.pcflash, cloud-native build from c6cbe98c0d93095b193b24e133cc9831c190fed4. Independent GitHub Android run 39761662276 succeeded. Existing helper is reused; no second App. First USB default selection and explicit BLE board pairing are necessary. Subsequent recognized insertion prepares system full-screen consent. Human consent is mandatory. Cancel, stale session and detach revoke pending grants; detach stops USB-owned capture. Firmware flashing and phone commands never start automatically.

APK: https://d.zhangyue.site/apps/phone-controller-flash/releases/1.0.8/phone-controller-flash-1.0.8-vc9.apk

50771037 bytes; SHA256 d69b4fb8032ee6d3c5ba5ba372fc718b6b9f34f9bb1d280857ef82f4ad966e5c. Actual signed APK certificate/version/USB manifest/filter verified; 21 original PNG contents unchanged. Public store, detail page and full downloaded APK verified. 29 Flutter tests and 140 Python tests passed. Bounded DeepSeek review found no blocking findings.

Evidence: /opt/phone-controller-release/2026-10-22-usb-screen; publishing receipt: /var/lib/download-publisher/pcflash-1.0.8-review on 124. Private firmware server1 generation74 unchanged; image integrity verified. Source docs commit follows release source and does not change binary.

Pending physical acceptance: cover installation/data preservation, Android USB default launch, first pairing, system full-screen selection and actual frames; App UI BLE OTA; actual WeChat HID search/stop/result and original IME restoration. No physical success inferred from unit tests. ADB remains restricted to Chinese input; no ADB install, screenshot or phone control used in this release task.
