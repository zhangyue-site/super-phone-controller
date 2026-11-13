# App 1.4 UI and pairing candidate

This is a review candidate, not a production rollout.

- Android and iOS share the natural-language phone-task entry: no slash command is required. A concrete target is shown before confirmation; detailed agent steps are generated after checking the current scene.
- Fixed four-digit binding codes are persistent. Short codes are requested explicitly with format=pin4; legacy clients retain one-use long-code issuance.
- Controller binding capabilities are separate high-entropy secrets, stored using Android Keystore encryption or iOS Keychain. The server stores only their hashes. Restoration requires the target to be currently authorized. Changing codes or revoking controllers invalidates existing bindings.
- Target-side progress is a public task summary with source, phase and observation timestamps. Missing timestamps/source are unknown. Active execution takes precedence over a newer pending draft.
- A command receipt is not success. Server cancellation is not proof of a physical stop. Without device evidence the UI keeps stop confirmation pending.
- Android local OCR and local recognition lifecycle are retained. The current iOS target does not provide equivalent local OCR and labels this limitation explicitly.
- Cloud builds use standard GitHub-hosted runners. Both platform jobs require regressions before build and encrypt artifacts. Android signing identity and package identity are preserved. The iOS artifact is an unsigned review IPA, not a TestFlight/App Store upload.

## Compatibility and deployment

App and backend changes form one candidate. New pairing/progress endpoints are not active until the backend is separately approved and deployed. Configure EPAPER_PAIRING_STATE to a private persistent SQLite path. Never publish the database or runtime credentials. Existing capture, HID permissions, firmware and STOP recovery mechanisms remain authoritative.

A passing build is not device acceptance. No capture authorization, USB/HID/BLE action, phone installation, service restart, firmware update, release publication or update-pointer activation is performed by this change.

## Sampling experiment integration

The Android SourceBurst implementation and lifecycle cleanup from source revisions
6e48598 and be86fb1 are retained, including their standalone boundary regression.
PCFLASH_SOURCE_BURST is explicitly 0 in this UI review build. This does not
activate the experiment or claim device acceptance. Existing observation
freshness, exact scope/frame association and HID permissions remain unchanged.
The separate sampling candidate used build number 70; the UI candidate uses 71.

## Observation preview and result evidence

A paired running task can request its current frame explicitly. The client
validates task identity, sequence/barrier, size and JPEG SHA-256; stale async
responses are discarded when the task changes or stops. This is a one-shot
observation, not a final result image. No screenshot polling or phone input is
introduced. The service does not yet expose an immutable final-result frame;
completion therefore does not pretend the last preview is verification evidence.
