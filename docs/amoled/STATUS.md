# AMOLED hardware port status

## Installed firmware

Version **0.1.7-amoled** was built, verified and flashed to the authorized test
board. [Verified cloud build](https://github.com/zhangyue-site/super-phone-controller/actions/runs/41306988761),
source `3ac10527f548e9b16b3a1c72d54fd22934a2c4df`.
Full image SHA256: `6db223e4906147c4c410fdd2e4585c44def455909ae766019ebb1b8e41409855`.

## Confirmed on hardware

- CDC status, 17 protocol cases, import/version/duplicate checks and storage limits.
- Four test plugins and their parameters survived a software restart.
- A 125-second run with 61 samples kept USB online, uptime increasing, input
  disabled and early crash count zero. Heap changed by only 64 bytes during
  that observation. This does not establish long-term leak freedom.
- Seven 480×480 device-rendered buffers were visually inspected: previously
  damaged text is clear. Controls are inset for the round screen and button
  text uses the full font line height. Synthetic test plugins were removed.
- Software maintenance acknowledged entry, then accepted a real ROM connection
  without an external reset. A software-controlled reset returned to the app.

The rendered buffers are **not photographs of the physical panel**. The user
reported a black panel while 0.1.6 remained responsive over USB. After flashing
0.1.7, physical panel emission and touch still require direct observation;
they must not be inferred from USB or screenshots alone.

## Fixed failures and regression prevention

The startup panic was a linker collision: application `usb_read` and `usb_write`
resolved to ESP32-S3 ROM absolute symbols. The retained panic pointed to the main
receive loop. Application functions now use the `amoled_usb_` prefix. CI checks
all 11 exported USB operations in the actual linked ELF for application code
addresses, separately from successful compilation.

0.1.6 snapshots showed corrupted glyphs. The 0.1.7 image uses uncompressed
Chinese bitmaps and one software draw unit, avoiding the compressed decoder's
shared RLE state. All seven new page buffers are clear; old failed evidence
is retained privately.

Three repeated early application crashes request hardware download mode.
RTC crash count and retained panic/log evidence have been read successfully
from ROM. Healthy runtime clears the crash count. Factory backup and
identity-bearing diagnostics remain private. This recovery path covers
application crashes, not every possible power or pre-application boot fault.

## Scope and unverified items

Implemented: manufacturer display/touch initialization, generic home screen,
persistent plugin descriptions, CDC JSON import/removal, gated manual USB
mouse/consumer reports, and render snapshots. Imported descriptions do not
execute code or start tasks automatically.

Still to integrate: phone-side plugin import, authenticated BLE relay, voice,
server workflow runner and phone screen-sharing state. Physical touch, actual
phone HID, battery operation, OTA and real bookkeeping have not passed
end-to-end acceptance for this port. No two-second transaction claim is made.

Host C regression uses real cJSON with AddressSanitizer and UndefinedBehaviorSanitizer.
It covers the protocol fixtures, numeric boundaries, malformed/trailing JSON,
parameter retention and mocked storage failures. Hardware results above remain
separate from these host tests.
