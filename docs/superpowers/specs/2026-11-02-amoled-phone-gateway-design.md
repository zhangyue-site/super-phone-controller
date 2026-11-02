# AMOLED phone gateway and BLE upgrade

The phone is the network gateway. Control packets and receipts use BLE; HID uses USB; MediaProjection images and model packages never traverse board BLE. No phone production ADB or accessibility input is introduced. The user's existing approval covers development; firmware activation remains a separate acceptance step.

## Deliverable
Implement target-specific authenticated BLE OTA using the existing helper UUIDs (0002 control, 0003 status, 0009 authorization), ordered bounded flash worker and strict AMOLED project/size/version checks. Reuse NVS identity and add PCOTA-AUTH2 image-bound authentication (fixed project, exact version, size and SHA256; preserve legacy PCOTA-AUTH1 for e-paper); authorization expires, is connection-bound, consumed by BEGIN and revoked by disconnect/STOP. Reject input during OTA, cancel writes before the boot-slot commit boundary, preserve USB descriptors and NVS. Report actual partition imageState. Mark new boot valid only after USB, display and BLE startup plus 30 seconds of healthy observation (initialization success, not requiring a connected USB host); pending image startup failure invokes rollback.

Flutter validates the connected board target before upload, retains old e-paper validation, supports semver AMOLED versions and 6 MiB slots, and waits for exact new boot/version/ELF/valid state. Server release validation must use a private target registry; never infer permission from metadata or accept e-paper firmware for AMOLED. No public device identity or release pointer activation.

## Transport capacity
Each signed control write is 48 bytes. Budget receipts at 512 bytes and three reads per action: at ten actions/s the BLE application payload is below 16 KiB/s. This is a planning workload, not measured board throughput. Serialized request/receipt latency is the practical acceptance metric. OTA is exclusive with control; phone fetches image through HTTPS before BLE transfer. No image/video/model bytes use control BLE. Voice is deferred until its codec and latency budget are specified.

## Model status
Private button-model deployment is managed independently of this source tree. Absence here does not establish whether a phone model is installed; verify the actual target phone files, loaded model hash and inference process before changing deployment. It detects button geometry and cannot independently authorize actions or choose semantic targets. The mobile inference integration is a separate next unit after transport/upgrade tests, with screenshot freshness, confidence, target matching and post-action verification. No claims about mobile speed from training validation metrics.

## Validation
Host tests exercise the actual OTA state machine with fake flash: authentication, size/target/version, ordered writes, overflow/truncation, hash failure, disconnect/STOP, timeout, cancellation during validation, failed commit and successful switch/restart. Flutter target-image validation tests cover both board families. Cloud CI compiles the independent target. Physical flash and phone tests are recorded separately.

Authorization tests must cover the helper busy-state signing path. A one-use BEGIN grant is distinct from an active authenticated transfer; DATA/END retain only the same connection epoch. CANCEL and local STOP do not require a fresh grant. Hardware performance remains pending; record p50/p95 command-to-receipt and actual OTA bytes/time with phone/MTU/version.
