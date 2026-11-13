import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/relay_phase_trace.dart';

/// Ported from the 2026-11-12 heartbeat candidate harness.
void main() {
  test('phase trace is fixed-field, monotonic and never leaks messages',
      () {
    var ms = 0;
    final events = <Map<String, Object>>[];
    final trace = RelayPhaseTrace(
        onEvent: events.add, elapsed: () => Duration(milliseconds: ms));

    trace.begin('maintenance', op: 12);
    ms = 300;
    trace.phase('write');
    trace.markWriteStarted();
    ms = 450;
    trace.fail(TimeoutException('SECRET'));
    final failure = events.last;
    expect(failure['stage_ms'], 150, reason: 'monotonic stage timing');
    expect(failure['failure_kind'], 'maintenance_unconfirmed');
    expect(failure['write_started'], true);
    expect(events.toString().contains('SECRET'), false);

    events.clear();
    trace.begin('poll');
    trace.setAction(1, 2);
    trace.phase('ack');
    trace.markWriteStarted();
    trace.fail(TimeoutException('SECRET'));
    expect(events.last['failure_kind'], 'input_outcome_unknown');

    events.clear();
    trace.begin('poll');
    trace.setAction(1, 3);
    trace.fail(StateError('SECRET'));
    expect(events.last['failure_kind'], 'input_not_dispatched');

    trace.finish();
    expect(events.last['reason'], 'phase_failure');

    // A throwing observer must never change the transport outcome.
    final observer =
        RelayPhaseTrace(onEvent: (_) => throw StateError('observer'));
    observer.begin('maintenance', op: 12);
    observer.fail(TimeoutException('x'));
  });
}
