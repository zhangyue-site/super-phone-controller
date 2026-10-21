# Authorized App OTA

User authorizes implementation and full upgrade testing without manual firmware transfer. Keep device firmware private, no long-lived credentials in APK, ADB only Chinese input.

Connect BLE, read INFO (.004) with protocol, device identity, full version, ELF SHA256, boot nonce and OTA image state. Cloud issues 32-byte random challenge, valid 120 seconds. AUTH (.005) accepts 32 bytes and returns HMAC-SHA256(device token, ASCII PCFLASH1 + newline + device + newline + raw challenge). App exchanges proof for a random 5-minute capability restricted to the immutable current device firmware SHA. No tokens in URLs. Challenge one-use, bounded storage and per-device outstanding challenges. Download verifies server size/hash and ESP image before BLE BEGIN. Connection proves local access at the same level as the existing local BLE updater; this adds no remote control authority.

BLE AUTH read/write and INFO read never expose device token. Clear proof on disconnect. Initial old firmware needs one maintenance update to add these characteristics. Old board gets a precise compatibility message, not anonymous fallback.

After READY, App waits for actual disconnection, reconnects the same remote BLE ID, reads INFO, and checks changed boot nonce, full version, ELF image identity and valid OTA state (2). Until then show waiting; timeout/rollback remains unconfirmed/failure. Cancellation does not claim rollback after commit.

Tests: real HTTP challenge/proof/replay/expiry/cross-device/immutable artifact/hash and existing bearer endpoints; Dart download/status polling with injected transports; cloud IDF + Flutter CI. Hardware test requires physically connected powered target S3. Real phone App acceptance reported separately from desktop BLE test.
