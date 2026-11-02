# Full platform and board parity implementation plan

> For agentic workers: use superpowers:subagent-driven-development or executing-plans task by task.

Goal: implement missing iOS/Android and AMOLED/epaper capabilities without removing the stronger platform's functions or claiming unsupported hardware success.
Architecture: shared Flutter role/task/model contracts; platform-native consent and capture adapters; board-local authenticated HID and update safety; private server registry and signing.
Tech stack: Flutter/Dart, Swift/UIKit/ReplayKit, ESP-IDF/C, Python service, GitHub Actions macOS/Linux.

The user explicitly authorizes autonomous implementation and requires all missing functions aligned. No repeated design permission. TestFlight restricted to the two exact user emails in server-private project roster, never public links. Production action through board HID, no accessibility/ADB controls. Builds through GitHub Actions only.

- [ ] iOS native app/preferences/version/settings bridges, explicit honest USB capability errors.
- [ ] iOS ReplayKit Broadcast Upload Extension, user initiated capture, private App Group capability transport, bounded JPEG upload with barrier/sequence/freshness, stop/renew/status; no silent capture.
- [ ] iOS target role integrates BLE identity and capture without inventing USB CDC presence. Real iOS USB HID behavior must be physically verified and is not inferred from BLE.
- [ ] Finish controller model planner hint consumer, client lifecycle review, full regression, private weights never embedded.
- [ ] Fix GitHub iOS dependency/build pipeline, stable public example bundle, private signing on106, versioned artifact. No credentials or private config in public artifacts.
- [ ] GitHub Android+iOS builds of fixed source revision, artifact/hash/native library verification, prepare private signing/upload and exact two-account TestFlight.
- [ ] AMOLED direct Wi-Fi/OTA parity: inspect current board drivers/memory, separate adapter, preserve HID/STOP/OTA mutex, test protocol and hardware.
- [ ] AMOLED audio and plugin workflow parity: establish actual microphone/speaker hardware before adapter; authenticated workflow task invocation with same consent/STOP boundaries.
- [ ] Common physical acceptance across boards/platforms, including detach/background/reconnect/OTA cancellation and fresh result verification.
- [ ] Record genuine Apple login, system grant and missing hardware blocks separately while continuing independent work.

Evidence rules: source implementation, CI build, deployment, installation, real phone result are distinct. Platform restrictions are investigated against official docs, never used to quietly exclude required target role.
