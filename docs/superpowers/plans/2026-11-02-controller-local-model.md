# Controller-phone local model plan

- [ ] Backend: private manifest/model, paired-controller frame/results endpoints, current-frame binding, observation-only consumer; isolated HTTP/security tests.
- [ ] Flutter: private model cache/download, portable postprocess and persistent inference isolate, tests for malformed/stale/cancellation paths.
- [ ] Controller UI: lifecycle-owned model state, active task loop; target role does not infer; widget tests.
- [ ] Stage current private v3 model on the server after computing its real hash and schema; no retraining, no modification of existing service.
- [ ] Verify Python/Flutter, real private ONNX inference, source privacy, Android signed build and iOS build/TestFlight preparation.
- [ ] Review final code, retain artifacts privately and report physical acceptance gaps explicitly.
