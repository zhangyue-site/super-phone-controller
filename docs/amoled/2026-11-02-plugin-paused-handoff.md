> Historical paused snapshot. Resumed 2026-11-03; see 2026-11-03-plugin-execution-candidate.md for current verified status.

# Plugin execution paused handoff

Paused at root request while iOS startup crash takes priority. Do not infer that
this candidate passed formal CI or physical acceptance. All plugin changes are
UNCOMMITTED in this isolated worktree, based on c2bf8b0:
branch codex/plugin-execution-20261102.

Implemented candidate (0.6.0-amoled):
- device-authenticated /board-plugin prepare/confirm/status/stop;
- private CONTROLLER_PLUGIN_WORKFLOWS alias registry, default empty/missing
  fails closed; strict text-only parameters, existing safe navigation templates;
  no shell, path, URL, arbitrary Python or external-side-effect runner;
- device/boot/gesture session, consumed request IDs, one-use confirm nonce,
  120-second confirmation, bounded owner lifetime; changed registry rejects
  pending confirmation; pending STOP does not cancel another origin;
- USB imported descriptor -> local preview -> explicit confirm -> existing
  REMOTE queue and direct worker; successful queue response precedes local USB
  permission. Direct enable_task fences the consumed task_id.
- real pending/queued/running/verified result/error/STOP text in board page;
  no import auto-run, no invented phone import. Confirmation disabled until
  actual pending response.
- local STOP revokes generation/USB and sends a bounded best-effort server stop;
  late responses cannot restore pending state.
- private allowlist and actual business configurations were NOT created.
  Phone BLE import, financial/message business runners, speech-to-plan reuse and
  playback remain unimplemented, not counted as complete.

Tests actually observed:
- tests/test_plugin_workflow.py: 7 passed before the final capacity regression
  was added. Current file contains 8 tests; the last capacity addition and tiny
  production change preserving STOP at capacity HAVE NOT YET BEEN RUN.
- tests/test_plugin_http.py: 2 passed (real localhost HTTP, synthetic identity/
  registry, no real model or external workflow).
- tools/test_amoled_plugin.py: passed ASan/UBSan for production lifecycle with
  fake server, plan before confirm, exact task permission, STOP/late reply,
  missing private registry and local-permit failure.
- tools/test_amoled_plugin_transport.py: passed ASan/UBSan for production HTTP
  adapter (TLS setup/redirect/response bounds/partial writes/cancellation).
- tools/check_amoled_plugin_syntax.py: whole worker host syntax passed.
- tools/test_amoled_direct_owner.py and check_amoled_direct_syntax.py passed
  after adding expected-task permit guard.
- tools/test_amoled_registry.py and tools/test_amoled_font.py passed.
- No final broad regression has been run after all last edits.

Known integration notes for resumption:
1. Run all current plugin tests and diff-check, then readonly review before
   committing. Formal firmware builds only GitHub Actions.
2. tests/test_remote_http.py includes the root-approved test-only ASR fixture
   fix (before=dict(jobs), assertEqual jobs) for subclass reuse. No production
   ASR behavior was changed in this plugin slice.
3. Only safe navigation text workflows are currently allowlist-supported;
   registering a bookkeeping alias will not magically supply a business runner.
4. Current UI/worker/task lifecycle still needs formal ESP-IDF compile, task/
   memory measurements, touch acceptance and actual phone/board tests.
5. Existing >=32KiB internal-heap health gate and USB/capture/OTA protections
   remain. No physical heap, successful action, flash or deployment claimed.
