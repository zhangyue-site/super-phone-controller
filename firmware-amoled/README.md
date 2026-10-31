# AMOLED plugin controller

Independent ESP32-S3-Touch-AMOLED-2.16 target; do not flash the e-paper binary.
Hardware BSP: Waveshare component 2.0.1, official example reference at commit
225a62bff11b5d0a0b607873860d39485a9a9685 (Apache-2.0).

This first hardware port provides a touch home screen, empty-by-default plugin
registry persisted in NVS, versioned JSON import/removal over USB CDC, and manual
USB mouse/consumer controls after local long-press consent. USB descriptors remain
fixed when input is stopped. Radio interfaces default off; no old device token is
embedded. Imported descriptions cannot execute arbitrary code.

Not yet integrated: phone-side import, authenticated BLE relay, server runner,
audio/voice transport and phone screen sharing. Their UI reports unavailable;
there is no simulated transaction, task success or shared-screen indicator.

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
