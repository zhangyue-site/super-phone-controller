# Upgrade failure investigation (2026-10-21)

The public HTTPS entry and authenticated firmware API were hosted separately. Added only the /phone-controller/ reverse-proxy route on the configured entry host, preserving Authorization, Host, SNI and TLS verification (depth 3). Config backed up before modification. nginx config test passed; reload succeeded. Unauthenticated public manifest now returns 401 rather than HTML 404. All unrelated configuration tokens verified unchanged.

This does not fix anonymous App firmware download: the App has no device credential and still receives 401. Do not publish embedded device credentials or embed a shared token in the APK. Authorized App delivery remains pending.

Local ci55 app.bin SHA256: 7386e126d6b4cd05e70872b9a85014e662c6261108c91569f670afda0d93b767. Only app.bin is suitable for BLE; APK, ZIP, bootloader and full-flash images are not.

BLE connection with MTU 517 was observed previously, but no BEGIN/transfer completion was observed. User-side upgrade acceptance remains unverified. No new firmware flashed during this investigation.
