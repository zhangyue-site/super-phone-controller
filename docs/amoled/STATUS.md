# AMOLED hardware port status

Firmware 0.1.1-amoled builds successfully from source
`130c979660d789fc8c308a20c0d1aee80662f82a`.
[Verified cloud build](https://github.com/zhangyue-site/super-phone-controller/actions/runs/41215991753).

The first 0.1.0 image was written to the authorized test board and passed the
chip's write digest check. USB did not enumerate after reboot, so startup and
functional acceptance have **not passed**. Version 0.1.1 disables both primary
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
