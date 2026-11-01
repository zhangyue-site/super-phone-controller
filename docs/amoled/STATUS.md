# AMOLED hardware port status

## Current build and software

Firmware **0.2.1-amoled** is installed on the authorized ESP32-S3-Touch-AMOLED-2.16.
[Cloud firmware build](https://github.com/zhangyue-site/super-phone-controller/actions/runs/41316004069),
source `919b6e902cec6fec48127c7966f8811a156c3791`.
Application SHA256: `1266873d7a18a3f1ff0d4ad61fdb90663b5ee7d3f74c48ace06dc286eb9496b4`.
Only the application slot at 0x20000 was written; NVS and OTA metadata were
read before/after writing and matched.

Android helper **1.2.11 (33)** supports this board and the existing Epaper boards.
[Signed helper build](https://github.com/zhangyue-site/super-phone-controller/actions/runs/41316004859).
The production package and signing certificate are unchanged.
[Download page](https://d.zhangyue.site/apps/phone-controller-flash/).
Installation and actual phone control remain separate acceptance steps.

## Implemented

- Independent NVS-provisioned identity with PCUSB and PCFLASH1 challenge proofs.
- PCBLE1 authenticated local control, sequence replay protection, signed receipts,
  heartbeat lease, cancellation, and release on disconnect.
- Fixed CDC + keyboard/mouse/consumer + separate Android touch interface.
  ARM/DISARM gates input without USB re-enumeration.
- Absolute touch click/drag and bounded keyboard/ASCII commands; successful
  input receipts wait for USB transfer completion.
- Separate image acquisition, bounded newest-frame encoding/upload, and status
  polling lanes in Android. Obsolete frames still respect the action barrier.
- Control authorization no longer depends on a firmware download release.
  Firmware download and upgrade capabilities keep their separate scope.
- Live USB/BLE/relay display status; screen-sharing status is checked on the phone.
  This board currently uses USB maintenance for firmware updates.

## Verified on the physical board and 106

- USB/BLE identity and challenge proofs, signed receipts, heartbeat, malformed
  signatures and replay rejection, ARM/DISARM without USB loss, real consumer
  transfer completion, unarmed pointer rejection, STOP, and nonce rotation.
- Ten production server-signed heartbeat round trips through a temporary Mac
  physical BLE transport: median 360 ms, maximum 364 ms. This excludes Android
  and phone UI response and is not a bookkeeping benchmark.
- Final firmware: 126.81-second observation, 60 samples, USB online, uptime
  increasing, early crash count zero, no free-heap drift in the sample window.
  Internal free heap stayed above 113 KB; minimum-ever internal free heap was
  94 KB. This does not establish long-term leak freedom.
- Heartbeat expiry and BLE disconnect release input while retaining USB.
- Synthetic plugin and parameters survive software restart; cleanup removed
  only the synthetic plugin. Provisioned identity survives upgrade and reboot.
- Seven 480×480 device-rendered buffers inspected, including the new state and
  settings text. These buffers are not photographs of the physical panel.
- 33 server authorization/OTA/relay regressions; Android analysis and CI
  regressions, native USB compatibility checks, and sanitizer host checks.

## Remaining acceptance

The board was tested while attached to the Mac. Actual Xiaomi phone tap/drag,
Android replacement installation, continuous MediaProjection capture, reconnect
and end-to-end latency require the board to be connected to the phone and the
system grant accepted. No two-second transaction claim is made.

Phone-side plugin import, board-initiated server workflow execution and voice
remain unimplemented. Stored plugin descriptions do not execute automatically.
Battery operation, physical touch and OTA require their own tests.
No bookkeeping save was performed during this work.

## Recovery and prior fixes

USB application exports retain the `amoled_usb_` prefix; CI checks the actual
linked symbols to prevent the previous collision with ESP32-S3 ROM USB names.
The uncompressed Chinese font and single software drawing unit are retained.
LVGL drawing stays in cached PSRAM text to leave internal instruction RAM for
BLE and exception vectors.

Repeated early crashes request ROM recovery. Software maintenance and reboot
work without physical buttons in the tested setup. Factory backups and
identity-bearing diagnostics remain private. The earlier 0.1.7 physical-panel
recovery was confirmed by the user; current rendered-buffer checks do not
replace physical-panel observation.
