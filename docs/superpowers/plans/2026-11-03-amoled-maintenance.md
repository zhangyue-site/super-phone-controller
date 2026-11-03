# AMOLED maintenance Implementation Plan
> For agentic workers: use subagent-driven-development for isolated driver and client work; integrate with verified host tests and cloud builds.
**Goal:** Make version/reinstall and board power maintenance understandable and functional.
**Architecture:** Shared image validation with a syntactic version policy; main owns UI and power sequencing, a PMIC driver owns register access; Android independently owns explicit version confirmation.
**Tech Stack:** ESP-IDF 5.5.2, LVGL 9.6, Waveshare BSP 2.0.1, C host regressions; Flutter Android.
- [x] Add failing host cases for same/older versions and cancellation/commit power policy.
- [x] Add version/power policy headers, preserve image-bound checks in ota_ble.c, verify host cases.
- [x] Implement isolated power.c/power.h using the existing shared I2C bus; test register changes and diagnostic returns.
- [x] Modify main.c: settings version, power menu/confirmation, pending request sequencing outside LVGL lock, safe cancel/abort.
- [x] Run tools/test_amoled_ota.py, tools/test_amoled_power.py and existing interlock/direct/wifi tests; inspect diffs and source privacy.
- [ ] Commit scoped files, cloud-build a new firmware revision and validate version/target/digest/artifact.
- [ ] Publish for the confirmed private target. If a bootstrap board flash is required, preserve recovery and do not perform an unconfirmed power-off.
- [ ] Integrate reviewed Android confirmation/diagnostics branch, CI signed build, same-signer public delivery and full download readback.
