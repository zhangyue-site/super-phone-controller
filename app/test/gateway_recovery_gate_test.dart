import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:pcflash/gateway_recovery.dart';

void main() {
  test('singleflight bounded backoff never runs after cancellation', () async {
    var now = Duration.zero, calls = 0, valid = true;
    final gate = GatewayRecoveryGate(elapsed: () => now);
    final pending = Completer<void>();
    Future<void> run(Future<void> Function() check) async {
      calls++;
      await pending.future;
      await check();
    }

    expect(
        await gate.tick(
            eligible: () => true, guard: () async => valid, run: run),
        false);
    now = const Duration(seconds: 2);
    final a =
        gate.tick(eligible: () => true, guard: () async => valid, run: run);
    final b =
        gate.tick(eligible: () => true, guard: () async => valid, run: run);
    await Future<void>.delayed(Duration.zero);
    expect(calls, 1);
    valid = false;
    final cancelled = gate.cancel();
    pending.complete();
    expect(await a, false);
    expect(await b, false);
    await cancelled;
    now = const Duration(hours: 1);
    expect(
        await gate.tick(
            eligible: () => true, guard: () async => true, run: run),
        false);
    expect(calls, 1);
  });
  test('transport failures keep retrying; protocol errors do not retry',
      () async {
    var now = Duration.zero, calls = 0;
    final gate = GatewayRecoveryGate(elapsed: () => now);
    Future<void> run(Future<void> Function() check) async {
      calls++;
      throw http.ClientException('test transport');
    }

    await gate.tick(eligible: () => true, guard: () async => true, run: run);
    for (final seconds in [2, 6, 14, 60]) {
      now = Duration(seconds: seconds);
      await gate.tick(eligible: () => true, guard: () async => true, run: run);
    }
    expect(calls, 4);
    expect(gate.exhausted, false);
    gate.reset();
    calls = 0;
    await gate.tick(
        eligible: () => true,
        guard: () async => true,
        run: (_) async {
          calls++;
          throw StateError('identity changed');
        });
    now += const Duration(seconds: 2);
    await gate.tick(
        eligible: () => true,
        guard: () async => true,
        run: (_) async {
          calls++;
          throw StateError('identity changed');
        });
    now += const Duration(hours: 1);
    await gate.tick(eligible: () => true, guard: () async => true, run: run);
    expect(calls, 1);
  });
  test('BLE link failures keep retrying while the physical session is valid',
      () async {
    var now = Duration.zero, calls = 0;
    final gate = GatewayRecoveryGate(elapsed: () => now);
    Future<void> run(Future<void> Function() check) async {
      calls++;
      throw const BleReconnectFailure('android-code: 133');
    }

    await gate.tick(eligible: () => true, guard: () async => true, run: run);
    now = const Duration(seconds: 2);
    await gate.tick(eligible: () => true, guard: () async => true, run: run);
    expect(calls, 1);
    expect(gate.exhausted, false);
    for (final seconds in [6, 14, 60, 3600]) {
      now = Duration(seconds: seconds);
      await gate.tick(eligible: () => true, guard: () async => true, run: run);
    }
    expect(calls, 5);
    expect(gate.exhausted, false);
    now += const Duration(seconds: 1);
    await gate.tick(eligible: () => true, guard: () async => true, run: run);
    expect(calls, 5);
  });
}
