# Plugin execution candidate: 0.6.0-amoled

Base c2bf8b0, isolated branch codex/plugin-execution-20261102.
This document supersedes the paused verification status in the handoff.
No live deployment, firmware build, publication, flash or physical acceptance
has been performed for this candidate.

## Implemented closed execution slice

USB CDC import remains the existing bounded versioned plugin-descriptor registry.
Import does not run a workflow. The detail page now requests "预览任务计划";
a separate page displays the real server plan, enables explicit confirmation
only after pending is returned, and reports actual queued/running/verified/error
or STOP responses. Imported ui.running/complete metadata is never execution proof.
The local worker is allocated only after an explicit preview gesture.

The server /board-plugin POST endpoint authenticates the existing device bearer.
CONTROLLER_PLUGIN_WORKFLOWS points to a server-private allowlist; missing/empty
configuration rejects with an explicit not-configured response. There is no
public registry, URL/path runner, arbitrary script, shell or Python import.

An allowlisted alias currently expands only to an existing RemoteControl safe
navigation text plan. Parameters must exactly match a bounded private text
schema, with bounded Han/ASCII alphanumeric/space values. The resulting task
still passes RemoteControl.prepare's supported-operation parser and the existing
planner/HID/visual-verification gates. Unknown aliases, path-like aliases,
unknown parameters, malformed types, oversized values and template field access
are rejected. This slice does not implement bookkeeping/message/financial
business runners and does not claim they work merely by registering an alias.

Synthetic configuration shape for tests/documentation only:

    {"synthetic.search": {
      "text": "打开设置搜索{query}",
      "parameters": {"query": {"type": "text", "maxLength": 16}}
    }}

No real allowlist, network config, device token or personal workflow was created.

## Device, gesture, confirmation and STOP boundaries

Each preview uses a fresh 32-hex gesture session plus the board's random boot
identity. Server identity binds device+boot+session. Request IDs are consumed
before side effects. The returned task and one-use confirmation nonce expire
after 120 seconds; confirmation rechecks the private alias fingerprint and
parameters. Task status is owner-scoped. Retired sessions are not evicted for
replay, and lifetimes/capacities are bounded.

Only a successful queued response to that explicit local confirmation enables
the existing direct worker, restricted to that exact task_id. It reuses existing
HTTPS device-authenticated claim/status/result/stop, not a new script runner or
BLE-style HMAC receipt. Unknown claim identity fails closed before any HID.
The fixed USB descriptor remains unchanged, so this path performs no
re-enumeration and cannot bypass a capture prepareUSB window. Existing capture
authority, fresh-frame/barrier, single-owner, local USB permit and OTA protections
remain mandatory in their existing layers.

STOP immediately revokes local generation and USB/direct permit and sends one
bounded server stop. No task creation, confirmation, uncertain response or
partial action is retried. Late replies cannot restore pending state. Wi-Fi loss
also revokes plugin generation; reconnect does not revive a previous gesture.
Only server-verified done is classified as completion.

A pending/expired plugin STOP cancels only its own plan; it cannot cancel another
origin's queued task. An active plugin's device stop retains the existing single
active-task behavior. STOP remains usable at the 512-request normal capacity.
A resumed audit also caught stopped sessions adding new flooded STOP IDs before
rejecting them; the new red/green test now proves that rejected stopped-session
traffic cannot grow the consumed-ID set.

The firmware marks automatic status polling and STOP I/O as in flight, preventing
a new local prepare racing a status response or stop completion. Prepare must return pending and confirm must return queued; unexpected transitions fail closed before local HID permission. The private
workflow map and task state are not written by device import.

## Actual verification on resumption (2026-11-03)

- Plugin server unit tests: 9 passed, including STOP capacity, stopped-session
  flood bounds, replay/session/nonce/expiry, private registry change, parameters,
  cross-device access and pending STOP isolation.
- Plugin real localhost HTTP tests: 2 passed, synthetic identity/allowlist;
  no actual model API or external-side-effect workflow.
- Related combined Python regression: 62 passed (plugin, remote task/HTTP,
  voice UI HTTP, paired authority and screen races/renewal).
- Relay gateway regression: 3 passed separately.
- Production plugin lifecycle and HTTPS host adapters passed AddressSanitizer
  and UndefinedBehaviorSanitizer checks.
- Whole plugin/direct worker host syntax checks passed; this is not ESP-IDF.
- Direct policy/owner/rejected disconnect, registry, font cmap, Wi-Fi transport/
  ingress, OTA engine and USB/HID interlock host checks passed.
- Python compile and git diff whitespace checks passed.

The root-approved ASR test-only fixture change is included: compare preexisting
mailbox jobs instead of asserting an empty mailbox in a reused base test.
Production recognition behavior was not changed by this plugin candidate.

## Remaining acceptance and feature gaps

Formal GitHub ESP-IDF compilation, physical task/heap measurements, touch
confirmation/scrolling, real shared-screen planning, USB HID results, concurrent
BLE/Wi-Fi/OTA/STOP and recovery remain unverified. The >=32KiB internal free-heap
health requirement was not lowered and no hardware numbers were invented.

Phone-side BLE descriptor import is not implemented; the existing phone-import
UI remains explicitly pending. A future management protocol must be restricted,
authenticated and host-contract-tested before exposing it. Speech text -> explicit
preview through an allowlisted alias can reuse this path later; recognition does
not currently invoke it automatically. Audio playback/mute/power sequencing and
real specialized business workflow implementations remain separate work.


## STOP permission-installation race review

A deterministic review found the old worker could pass live(), pause before
direct enable, then resume after STOP and reopen USB. The new confirm gesture
captures the direct epoch. Enable and cancel share one short FreeRTOS mutex;
guarded enable checks that original epoch under the same lock before installing
the exact-task permit. Cancel advances epoch and closes USB under that lock.
The worker additionally requires permit_epoch == generation. No network I/O is
inside this synchronization boundary.

The regression first failed because an old epoch could still install a permit
after STOP; it now rejects without arming USB. A second production plugin
lifecycle test triggers cancellation immediately at the permission entry and
verifies gate stays false and the task is stopped. Prepare/confirm UI publication
is also generation-guarded. Readonly reviewer review_gateway_spec confirmed the
original P1 is closed and reported no new blocker from this fix.
