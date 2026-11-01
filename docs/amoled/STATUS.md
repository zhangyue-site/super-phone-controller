# AMOLED hardware port status

Firmware 0.1.2-amoled builds successfully from source
`0747c86c9f3358f285e5b8577d03f8ceae5fe9a0`.
[Verified cloud build](https://github.com/zhangyue-site/super-phone-controller/actions/runs/41256286122).

The first 0.1.0 image was written to the authorized test board and passed the
chip's write digest check. USB did not enumerate after reboot, so startup and
functional acceptance have **not passed**. Version 0.1.2 disables both primary
and secondary USB-Serial-JTAG console output, adds a configuration guard, visible
USB initialization errors and a local maintenance entry. Its binary and merged
image have been checked; it awaits physical BOOT recovery and board verification.
Factory backup and device-specific evidence remain private.

Implemented in code: manufacturer display/touch BSP, generic home screen,
persistent plugin descriptions with version checks, CDC JSON import/removal,
manual USB mouse/consumer input with a local gate, and render snapshots.
Imported plugins do not execute code or start a task automatically.

Still to integrate: phone-side plugin import, authenticated BLE relay, voice,
server workflow runner, and phone screen-sharing state. No real bookkeeping or
end-to-end two-second transaction performance is claimed for this port.

Host registry regression now runs the firmware C functions against real cJSON
under AddressSanitizer and UndefinedBehaviorSanitizer. It covers 17 protocol
fixtures plus numeric boundaries, malformed/trailing JSON, parameter retention
and mocked storage failures. An overflowing version component was found and
fixed; these host checks passed both on the cloud workspace and in CI.
They do not validate real flash failure atomicity, physical touch or phone HID.

The candidate exposes uptime and reset reason for continuous-run verification.
The first flashed image remains the installed version until a stable ROM
interface can be obtained. Physical startup, screen snapshots, real NVS
persistence and phone input have not yet passed acceptance.
