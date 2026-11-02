# iOS native parity contract and evidence

## Implemented source

The host `NativeBridge.swift` owns `pcflash/app`, `pcflash/usb`, and `pcflash/screen`. `CaptureContract.swift` handles an app-group container with atomic, mode 0600, excluded-from-backup files. `BoundedRequest.swift` is the ephemeral, response-bounded, redirect-rejecting HTTP transport. `SampleHandler.swift` receives ReplayKit sample buffers, without writing images or audio to disk. Only video buffers are consumed; microphone UI is hidden.

`pcflash/app`: `appearance` returns `system|light|dark`; `setAppearance({mode})` validates/persists; `info` returns `{versionName,versionCode}`; `openSettings` opens Apple's public app-settings URL; `openDownload` opens the configured HTTPS `DOWNLOAD_URL`, or reports `not_configured`. Diagnostic event payloads are deliberately not persisted; `diagnostics` currently returns an empty JSON array string. This is a documented diagnostics limitation.

`pcflash/screen`:

- `start({ticket,baseUrl})`: validates a 43-character screen-frames ticket and HTTPS endpoint; no user/password/query/fragment URL components. Rejects a USB session. Stores only this short-lived capability plus generation ID, wall-clock and monotonic expiry (270 seconds), and endpoint in the restricted App Group. The user sees an actual `RPSystemBroadcastPickerView`, must press it and confirm Apple's broadcast prompt. No subview traversal, synthetic UI events or private API. Future completes only after the extension publishes a matching active generation. Cancellation and 60-second timeout revoke the capability and return `cancelled`. Screen start is unavailable on iOS 27+ with an explicit `capture_os_unsupported` error.
- `status`: JSON string `{active,capture,task}`. Active requires a valid local capability and extension heartbeat updated within six seconds; merely presenting a picker never reports success.
- `stop`: first removes the local capability, cancels pending consent and requests `/app-screen/stop`. The extension checks the shared capability before frame work, on responses, and every second even if there are no video callbacks. It cancels work and calls `finishBroadcastWithError` on invalidation. A network request already sent cannot be recalled; server revocation and expiry remain authoritative. No old action is replayed.
- `renewCapture({controlTicket})`: requires the same active broadcast generation. POST `/app-control/screen-renew`, bearer target-owner control ticket, body exactly `{ticket: captureTicket}`; requires response `scope=screen-frames,expiresIn=300` before extending local deadline 270 seconds. The control capability is request-memory-only, never persisted in the App Group. This is the existing Android/server protocol (see `display_service/app_control.py` and `tests/test_screen_renew.py`), not an invented `/app-screen/renew`. Failed renewal preserves the prior expiry and cannot resurrect a STOP generation.
- USB-specific recovery/window methods return `usb_unsupported`.

`pcflash/usb.snapshot` returns `{attached:false,supported:false,platform:'ios'}`; proof/bind/mode operations return an explicit unsupported error. BLE identification remains a separate shared Flutter flow. No USB CDC session or iPhone HID success is inferred from BLE.

## Frame and action barrier protocol

POST `/app-screen/frame`, bearer screen capability, `Content-Type:image/jpeg`, `X-Screen-Sequence`, `X-Screen-Barrier`, and oriented native width/height. The full oriented image is scaled within 720×1280 at JPEG quality 0.7, maximum 524288 bytes. Exactly one upload and one newest pending sample are retained. No frame/audio archive or unbounded work queue exists.

The initial barrier is empty. Successful 200/202 responses must carry a 32-character lowercase hexadecimal barrier. After every acknowledged response, the host-clock watermark is advanced and all pending frames are discarded: the next sample must have a later ReplayKit presentation timestamp. This retains the server's action/fresh-frame sequence boundary. Sequence increments serially. Ordinary frames are throttled at 800 ms; a nonzero action barrier temporarily permits 100 ms. Geometry/orientation changes stop capture and require renewed user authorization. `/app-screen/status` is polled every two seconds with at most one in flight; response cap is 16384 bytes. Oversized task presentation is omitted to preserve the shared-state size bound. Frame/control responses cap at 4096 bytes. Redirects are rejected so bearer credentials are never forwarded to redirect destinations.

## Build and signing

The project now contains an embedded `ScreenBroadcast.appex` target, dependency, source membership, sample-buffer extension plist and two matching app-group entitlements. Deployment floor is iOS 15 to match the Flutter/native dependency baseline. Extension version derives from Flutter's Generated.xcconfig; no private provisioning or team identifier is committed.

Private GitHub Actions signing inputs must configure:

- `APP_BUNDLE_ID` (public default `org.example.phonecontroller`);
- `BROADCAST_BUNDLE_ID` (default `$(APP_BUNDLE_ID).ScreenBroadcast`);
- `CAPTURE_APP_GROUP` (default `group.$(APP_BUNDLE_ID).capture`);
- optional `CONTROLLER_BASE_URL`, `DOWNLOAD_URL` HTTPS URLs; Dart `start.baseUrl` supplies the actual capture endpoint;
- both app identifiers, App Group registration, and separate matching host and extension provisioning profiles. Do not globally replace `PRODUCT_BUNDLE_IDENTIFIER` for both targets with one identifier.

CocoaPods/ONNX runtime resolution and the macOS GitHub Actions build remain the main agent's scope. No iOS app was compiled on the local machine or development server in this task.

## Platform boundary and required acceptance

Apple's current documentation marks [RPSystemBroadcastPickerView](https://developer.apple.com/documentation/replaykit/rpsystembroadcastpickerview) deprecated, referring to ScreenCaptureKit's sharing picker, and [RPBroadcastSampleHandler](https://developer.apple.com/documentation/replaykit/rpbroadcastsamplehandler) as no longer supported. The current API metadata marks the iOS 27 boundary. This implementation supports the existing ReplayKit path on iOS 15–26; it does not claim iOS 27 capture parity. A separately compiled ScreenCaptureKit adapter and real iPhone validation remain required for iOS 27+. Controller/BLE functionality is not disabled by this capture restriction. Apple's [WWDC live broadcast sample-buffer explanation](https://devstreaming-cdn.apple.com/videos/wwdc/2018/601/601_live_screen_broadcast_with_replaykit.pdf) documents ReplayKit's system UI and extension architecture.

Required actual acceptance after signed CI artifact installation: cancel picker, confirm picker, foreground/background host, system Stop Broadcast, lock/unlock, offline upload, TTL expiry, renewal race with STOP, board detach as expressed through Flutter BLE ownership, rotate/restart, same-screen barrier freshness, both board types' real USB HID actions and fresh-frame verification. iPhone HID compatibility is unverified until physically exercised. System UI success, signing success and backend frame receipt must be independently recorded.

## Actual checks in this task

- Local offline `swiftc -frontend -parse` of all five Swift source files: passed. This parses syntax only, does not typecheck against Apple/Flutter SDKs and is not an iOS build.
- `plutil -lint`: Xcode OpenStep project, both Info.plists and both entitlements passed.
- Development server `python3 tools/test_ios_capture_contract.py`: 2 tests passed, covering bundle/App Group agreement and target dependency/shared-source/embedding graph. These do not simulate ReplayKit or claim device success.
- Official build, CocoaPods resolution, codesigning, App Store/TestFlight submission and physical phone acceptance: not performed by this subtask.
