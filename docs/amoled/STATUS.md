# AMOLED hardware port status

Firmware 0.1.6-amoled was built, verified and flashed to the authorized test
board. [Cloud build](https://github.com/zhangyue-site/super-phone-controller/actions/runs/41306274520),
source `41716e2d2e29bfe2c495d49bd127f384f0a42add`.

## Confirmed on hardware

- CDC status, 17 protocol cases, plugin import/version checks and storage limits.
- Four test plugins and their parameters survived a software restart.
- A 125-second run with 61 samples kept USB online, uptime increasing, input
  disabled, and early crash count zero. Test plugins were removed afterward.
- Seven 480×480 page snapshots were obtained, but visual inspection found
  corrupted glyphs. Display acceptance has **not passed**. A reported black
  panel coexisted with a responding application; panel output remains unresolved.

The startup crash was a linker collision: application `usb_read` and `usb_write`
resolved to ESP32-S3 ROM absolute symbols. The real panic pointed to the main
receive loop. Application functions now use the `amoled_usb_` prefix. CI checks
all 11 exported USB operations in the linked ELF for application code addresses.

## Display correction awaiting hardware verification

Version 0.1.7-amoled uses uncompressed Chinese glyphs, one software draw unit,
full font line height in buttons, and controls inset for the round screen.
[Candidate build](https://github.com/zhangyue-site/super-phone-controller/actions/runs/41306988761),
source `3ac10527f548e9b16b3a1c72d54fd22934a2c4df`. This candidate is not yet
claimed to fix the panel or pass visual acceptance.

Three repeated early application crashes request hardware download mode.
RTC crash count and retained panic/log evidence have been read successfully
from ROM. Healthy runtime clears the crash count. A normal software restart
and remote status have passed; the explicit maintenance-to-ROM command still
needs its own hardware acceptance. Factory backup and device evidence stay private.

## Scope

Implemented: manufacturer display/touch initialization, generic home screen,
persistent plugin descriptions, CDC JSON import/removal, gated manual USB
mouse/consumer reports, and render snapshots. Imported descriptions do not
execute code or start tasks automatically.

Still to integrate: phone-side plugin import, authenticated BLE relay, voice,
server workflow runner and phone screen-sharing state. Physical touch, actual
phone HID behavior, battery operation, OTA and real bookkeeping have not passed
end-to-end acceptance for this port.

Host C regression uses real cJSON with AddressSanitizer and UndefinedBehaviorSanitizer.
It covers the protocol fixtures, numeric boundaries, malformed/trailing JSON,
parameter retention and mocked storage failures. Hardware results above remain
separate from these host tests.
