# AMOLED plugin controller

Independent ESP32-S3-Touch-AMOLED-2.16 target; do not flash the e-paper binary.
Hardware BSP: Waveshare component 2.0.1, official example reference at commit
225a62bff11b5d0a0b607873860d39485a9a9685 (Apache-2.0).

This first hardware port provides a touch home screen, empty-by-default plugin
registry persisted in NVS, versioned JSON import/removal over USB CDC, and manual
USB mouse/consumer controls after local long-press consent. USB descriptors remain
fixed when input is stopped. Radio interfaces default off; no old device token is
embedded. Imported descriptions cannot execute arbitrary code.

Authenticated BLE relay is implemented; the 0.3.0 candidate adds image-bound BLE
OTA using the phone as its cloud gateway. See docs/amoled/STATUS.md for installed
versus candidate versions and exact acceptance evidence. Phone-side plugin import,
board-initiated server workflows and voice remain unavailable. Screen-sharing
status is checked on the phone, not inferred from a BLE connection.

Build on the configured cloud workspace using `.github/workflows/amoled-firmware.yml`.
The initial full image changes partition layout: back up all 16 MiB before writing.
Subsequent app-only OTA must use this target's own 6 MiB slots, not e-paper slots.
Never publish a factory backup or private identity/configuration in Git.

USB CDC protocol: newline-terminated JSON, maximum request 6271 bytes.

- `{"op":"status"}` returns actual version, USB/gate status and stored descriptions.
- `{"op":"import","plugin":{...}}` accepts format `phone-controller-plugin`,
  apiVersion 1, lowercase id, strict three-part version, name and
  runner `{ "type":"server-workflow", "entry":"..." }`.
- `{"op":"remove","id":"demo.example"}` removes that description.
- `{"op":"view","page":0}` selects a local screen (0 through 6) for diagnostics.

Four plugins maximum, total persisted JSON below 6144 bytes. Equal versions are
idempotent, downgrades rejected; upgrades retain existing parameters. Import does
not arm HID or start a workflow. STOP releases input and preserves USB enumeration.
Serial DTR/RTS is not a remote execution or re-enumeration trigger.

Diagnostics: snapshot returns a JSON header followed by RGB565 bytes and a newline.
This reads the device-rendered LVGL canvas; it does not prove physical panel pixels.
Maintenance restart/bootloader requires the exact USB serial in the device field
and disabled HID. Neither operation erases flash.
Font subset: Noto Sans CJK SC, SIL OFL; license included.

The Chinese font includes GB2312 common Han characters plus punctuation; rare
characters outside that set may still need a future dynamic font package.

Recovery: the maintenance command and local maintenance button disconnect the
OTG stack, release its internal PHY and give that PHY back to USB-Serial-JTAG
before entering ROM download mode. Three consecutive application panic/watchdog
resets before 30 seconds of healthy operation request the same recovery path.
Normal restarts do not count. The RTC policy is host-tested; hardware recovery
must still be verified on the board. Failures before application entry and
physical power/cable problems are outside that software recovery mechanism.

## Target-specific protected updates

Configure the server-private `CONTROLLER_FIRMWARE_TARGETS` JSON registry to map
a device identifier to `phone_controller_amoled`. Unknown devices retain the
legacy e-paper profile; malformed/missing configured registries fail closed.
Keep the registry and device keys outside Git. No release is activated by this
configuration alone. The helper downloads an immutable image via HTTPS and
obtains a one-use image-bound BLE grant. E-paper images cannot be transferred
to the AMOLED target. Current unsigned/full factory images are not BLE payloads.

Use `python3 tools/test_amoled_ota.py`, `python3 tools/test_amoled_interlock.py`
and `python3 tools/test_amoled_registry.py` for host checks; CI compiles the
independent target. These do not replace real phone upgrade/recovery tests.

## Wi-Fi maintenance slice (source candidate, not hardware accepted)

Wi-Fi station configuration and USB-requested Wi-Fi OTA are implemented in this
candidate. Direct Wi-Fi task/HID control and phone-triggered Wi-Fi updates are
not implemented: BLE `wifiOtaSupported` stays false and USB status explicitly
reports `wifiControlSupported: false`. A connected Wi-Fi station does not prove
a working cloud session. No image has been built, deployed or flashed by the
host tests below.

The local USB CDC parser accepts these maintenance operations only with the
exact USB serial in `device`, USB connected, HID disarmed, no OTA pending, and
no BLE controller connected:

- `maintenance.wifi.configure`: exact fields `op, device, ssid, password, endpoint`.
  The endpoint is an HTTPS origin or fixed path prefix, without userinfo,
  query, fragment, percent escapes, backslash or trailing slash. WPA2 credentials
  are stored in one bounded private NVS blob; they are never included in status
  or replies. Wi-Fi driver storage is RAM, avoiding a second credential copy.
- `maintenance.wifi.clear`: exact fields `op, device`; removes that blob.
- `maintenance.wifi.ota`: exact fields `op, device`; explicitly requests one
  download. It never arms HID. Failure, STOP, detach or loss of network cancels
  the epoch and never retries the image or resumes its chunks.

NVS namespace privacy is not encryption at rest: this candidate does not burn
eFuses, change partition layout or silently enable flash/NVS encryption. Physical
flash confidentiality still requires a separately reviewed provisioning policy.

The adapter uses the trusted ESP-IDF certificate bundle, normal certificate time
validation (updates fail closed until time is synchronized), no redirects, exact
HTTP 200 and content lengths, bounded manifest/image reads and a 120-second
transfer budget. The board token remains inside identity.c and is applied only
as an HTTP authentication header. Manifest and image use the same configured
HTTPS endpoint; the image is immutable SHA-bound. Wi-Fi chunks enter the existing
single OTA queue/engine, reusing hash, target/version checks, USB/flash mutex,
rollback and USB recovery. There is no new direct flash-writing path.

Host checks (AddressSanitizer and UndefinedBehaviorSanitizer):
`tools/test_amoled_wifi.py`, `tools/test_amoled_wifi_transport.py`,
`tools/test_amoled_wifi_ingress.py`, and existing OTA/control/interlock checks.
The transport tests execute production adapter functions against a fake TLS
client, including split reads, bad certificate result, redirect, invalid length,
chunked response, STOP during read, network loss, BLE ownership, timeout and queue
failure. They do not replace the GitHub Actions firmware compile, real TLS/Wi-Fi
test, simultaneous USB/BLE/STOP testing, physical update, rollback or recovery.

API references used:
[ESP-IDF HTTP client](https://docs.espressif.com/projects/esp-idf/en/v5.5.3/esp32/api-reference/protocols/esp_http_client.html),
[ESP-IDF NVS](https://docs.espressif.com/projects/esp-idf/en/v5.5.3/esp32s3/api-reference/storage/nvs_flash.html),
[official Waveshare BSP board](https://github.com/waveshareteam/ESP32-S3-Touch-AMOLED-2.16).

Candidate version: `0.4.0-amoled`, allowing a version-increasing update from the
installed `0.3.0-amoled`. With no saved configuration, startup allocates only a
small configuration mutex; Wi-Fi, network interface, SNTP and the 8 KiB worker
stack are deferred until configuration is explicitly saved. Configured-board
RAM usage still needs the Actions image plus real heap measurements. Existing
30-second boot acceptance continues to require display startup, USB, BLE/OTA
readiness and at least 32 KiB internal free heap; Wi-Fi is optional and cannot
fake a healthy image if that threshold fails.

The 120-second deadline also reaches the shared OTA writer: END is rejected when
over budget and the clock is checked again after image verification immediately
before the commit CAS. Tests cover a last DATA queue wait crossing the deadline
and verification itself crossing the deadline, with no boot-slot commit. After a
partial network-stack initialization failure this boot does not attempt duplicate
netif/event-handler initialization; saved configuration remains available for an
explicit maintenance restart. No successful network initialization is inferred
from saving that configuration.

## Confirmed plugin candidate

The 0.6.0 source candidate adds USB-imported descriptor -> private allowlisted
safe-navigation plan -> explicit board confirmation -> exact-task direct permit
and real status/STOP. Missing private configuration refuses to run. It does not
implement phone BLE import, arbitrary scripts or financial/message workflows.
See [candidate evidence and remaining acceptance](../docs/amoled/2026-11-03-plugin-execution-candidate.md).
No successful physical operation or deployed firmware is implied by this source.

## Opt-in automatic Wi-Fi updates

Private USB provisioning accepts a primary SSID/password and backupSsid/backupPassword, an HTTPS endpoint and an explicit autoUpdate boolean. Credentials stay in device NVS and must never be committed or printed. Existing single-network NVS configurations remain supported. Disconnected boards rotate between the two saved networks.

When enabled, idle boards check after one minute at startup, then at five-minute intervals. Only a higher valid AMOLED version is installed automatically; explicit maintenance can reinstall. Active HID, BLE, audio and direct-control sessions defer automatic checks. Transfers retain TLS, device authentication, digest/project/slot verification, a ten-minute overall budget and existing stalled-writer protection. Retry cooldown begins after an attempt finishes. USB, BLE and display startup health plus configured Wi-Fi initialization must pass before confirming a new slot.
