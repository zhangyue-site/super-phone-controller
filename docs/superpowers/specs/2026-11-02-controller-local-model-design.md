# Controller-phone local inference

User-approved roles: the controller phone runs the private button detector; the target phone supplies user-consented MediaProjection frames and receives ESP32 USB HID. The cloud authenticates, schedules and validates actions. Do not place inference on the target phone or embed model/keys in Git/APK. The user authorized autonomous development and release preparation, with no repeated design questions.

## Data and authority
Only a paired controller capability can request /app-local-vision/manifest, /model, /frame and /result (POST). Model manifest is server-private; binary download is immutable SHA256/size bound, <=32 MiB, no redirects or arbitrary URL. Fixed input [1,3,320,320], RGB float /255, stretch resize, output [1,5,2100] (xywh + button score). The model identifies geometry, not semantic intent.

A frame response contains task_id, frame_id (SHA256 of exact JPEG), barrier, sequence, width, height and jpegBase64; no disk screenshots. Only an active, confirmed, controller-owned task with live target consent and <=2 second frame age can be read. Results bind task/frame/barrier/model hash, max100 bounded normalized detections, explicit actual local timing; stale/revoked/STOP results are rejected. Results remain observation hints; never grant HID, authorize side effects or create a task. Existing cloud action signing/board HID gates and verification remain.

## Controller runtime
Use pinned cross-platform ONNX Runtime Flutter FFI integration with Android 16 KiB page alignment and iOS SwiftPM support; verify both platform builds. Models are fetched over authenticated HTTPS after pairing, hash checked and atomically cached in app-private storage by content hash. Controller performs JPEG decode, preprocess and inference in an isolate, validates exact tensor shape, finite coordinates/scores and NMS, and reports normalized boxes with the exact frame identity. The controller page owns a bounded one-in-flight observation loop only while the task is running. Stop, route disposal, backgrounding, authorization expiry and generation changes discard late results and close inference. Errors remain visible; no hidden remote inference substitution.

## UI and acceptance
Show download/loading/ready/inference/failed/paused state on the controller task page, actual inference milliseconds and detected count. No numeric speed promise or fake successful click. Target page never starts detector. Test private model manifest/download scope and tampering; revoked parent/STOP/frame freshness; NMS, geometry and malformed outputs; controller lifecycle/late completion; real model inference on a supported test host; cloud Android/iOS build and separate physical-phone acceptance.
