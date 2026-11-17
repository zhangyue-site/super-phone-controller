# NanoKVM-inspired diagnostics

Approved scope: read-only device diagnostics, additive claim wait reasons, fresh exec heartbeat. Preserve authorization, claim fences, screen bootstrap policy and STOP semantics.

1. Add failing tests for heartbeat missing/stale/future/latest boot and queued status.
2. Implement bounded heartbeat snapshot and compatible latest_exec.
3. Add claim reason tests and additive reason fields without changing op/lease.
4. Add authenticated app-control diagnostics operation with strict empty payload, no task mutation or phone actions.
5. Verify focused tests, auth and STOP regressions; export patch against source baseline. No deployment or firmware changes.
