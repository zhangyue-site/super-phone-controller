# AMOLED HTTPS direct-control candidate

Candidate version: 0.4.1-amoled.
Base: 91f2db2, isolated branch codex/amoled-direct-control-20261102.
This is source and host-test evidence. No firmware compile, deployment, flash or
real-phone acceptance has been performed for this candidate.

## Existing protocol reused

The adapter uses the e-paper paths without adding a transport protocol:

1. POST /remote/claim, body {"ready":true}, device bearer, X-Voice-Session
   (fresh random 16 hex per retired boot/turn), monotonic X-Voice-Sequence,
   X-HID-Pointer:absolute-v1 and X-HID-Keyboard:usb-v1.
2. The first response establishes the existing 64-hex X-Remote-Lease; only a
   subsequent claim made with that lease may consume op:start + task_id.
3. POST /remote/status must say op:wait immediately before each USB action.
4. POST /dialogue/poll retrieves a command once. Reserve its 32-hex ID locally
   before USB submission, including home/key/text and pointer.
5. POST /dialogue/result sends the existing {id,ok,output,error} acknowledgement.
   This is an HTTPS-authenticated device-bearer acknowledgement, not the BLE
   HMAC receipt. HID_REPORT_SENT does not claim a visual task success.
6. POST /stop retires the old session on local STOP/failure/completion. No
   retries: an ambiguous claim, result, partial request or partial HID fragment
   retires the entire local turn, gate and ID set before another local permit.

The existing server OWNERSHIP_LOCK/direct_blocked prevents cloud gateway/direct
task overlap. Firmware relay mux additionally refuses BLE attachment while a
direct owner is retiring. Existing BLE HMAC signing and acknowledgement stay
unchanged. No task is created or confirmed by firmware.

## Local safety boundary

A normal manual-input ARM never starts the network worker. The settings page
has a separate board-local 2-second long-press direct-control entry. It checks
Wi-Fi, identity, OTA engine readiness and no BLE/direct owner, then grants a
20-second idle claim window. A consumed task has a maximum 180-second local
budget. STOP, detach, cancellation, deadline or unknown result revoke the permit.
Another task requires another explicit local long-press.

The direct worker exists only after Wi-Fi configuration initializes networking.
It applies the identity token internally as an Authorization header; no token
getter, config export, credential log, private URL or network setting is added.

AMOLED is composite-fixed-v1: enabling/disabling its gate never re-enumerates USB
or changes descriptors. This adapter does not invoke prepareUSB, mode changes or
USB recovery. Therefore it never bypasses a pending capture preparation window:
it performs no operation that needs one. If descriptor/mode switching is added
later, the existing capture-owner/nonce/generation ready window must be completed
before switching. A Wi-Fi connection cannot imply target capture consent.

Server board_status previously returned running/wait after screen authority
expired. The minimal server change samples screen_ready before remote/mailbox
locks and cancels the matched running task when capture is no longer authorized.
The new regression first observed wait after expiry, then passed with cancelled.
No live server has been changed.

## Supported action slice and remaining gates

Runtime supports home, absolute click, bounded drag, printable ASCII fragments,
and the existing search-only key subset. Search text/key requires visible,
focused, non-password search target metadata. Every 8-character text fragment
gets a fresh status query. Absolute move/hover is rejected rather than simulated.
Chinese candidate recognition and later visual verification remain existing
server planner responsibilities; firmware never inserts arbitrary Unicode or
uses ADB/accessibility.

HTTPS verifies the certificate bundle and clock; redirects, chunked or >2048
byte response bodies, NUL JSON escapes and late generation results fail closed.
Commands have strict field/duplicate/bounds checks. ID and turn budgets are
bounded. OTA and HID use the existing USB mutex and existing shared flash writer.

Static wifiControlSupported and phone-triggered wifiOtaSupported remain false
until compile/integration review decides how to expose this partial candidate;
wifiDirectConnected reflects only a currently running direct task, not success.
The full foreground/phone UX, optional hover, physical heap measurement,
concurrent BLE/USB/Wi-Fi STOP, actual capture on Android/iOS, firmware compile,
rollback and recovery remain unverified. Source implementation does not replace
those checks.

## Reproducible host checks

- python3 tools/test_amoled_direct.py
- python3 tools/test_amoled_direct_owner.py
- python3 tools/test_amoled_direct_runtime.py --cjson-dir <existing cJSON host test directory>
- python3 tools/test_amoled_direct_transport.py --cjson-dir <same directory>
- python3 -m unittest discover -s tests -p test_remote_control.py
- Existing Wi-Fi transport/ingress, OTA engine and USB interlock tests.

The firmware GitHub workflow obtains pinned cJSON through the existing registry
test, then runs these new ASan/UBSan tests. Formal ESP-IDF builds remain GitHub
Actions only; this branch has not started a build.


Included registry fixture fix 9d9d715 as cherry-pick bacdeb4; this does not include or trigger a firmware build.

## Follow-up review fixes

Rejected/stale BLE disconnect handles are not current owners. The production GAP
disconnect branch now clears secrets and globally cancels only when its handle
matches the stored BLE owner. The regression first reproduced a rejected
newcomer cancelling the direct task, then passed while also testing that a real
BLE-owner disconnect still clears both keys and cancels safely.

The existing generator includes GB2312 plus all main.c characters. A new font
check reads the actual LVGL cmaps, including sparse lists and holes, and confirms
all 133 non-ASCII source characters and the new direct-control labels are already
mapped. No font regeneration was necessary; the font bytes are unchanged.
The check includes an intentionally missing/hole glyph negative test and runs
in firmware CI. This verifies glyph presence, not physical panel readability.

The existing configured-board boot acceptance still requires at least 32 KiB
internal free heap. No heap value has been measured or claimed for direct-control
hardware; that physical acceptance requirement remains open.
