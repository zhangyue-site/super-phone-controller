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
