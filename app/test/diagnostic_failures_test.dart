import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/cloud_relay.dart';
import 'package:pcflash/diagnostics.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  for (final status in [403, 409]) {
    test('HTTP $status close persists safe phase before error is returned',
        () async {
      final events = <Map>[];
      final ended = Completer<void>();
      var disconnects = 0;
      final messenger =
          TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
      messenger.setMockMethodCallHandler(SafeDiagnostics.channel, (call) async {
        if (call.method == 'diagnosticEvent') {
          events.add(Map.from(call.arguments as Map));
        }
        return null;
      });
      addTearDown(() =>
          messenger.setMockMethodCallHandler(SafeDiagnostics.channel, null));
      final relay = CloudRelay(
          post: (path, _) async {
            if (path == 'poll') {
              throw ControlHttpFailure(status, 'SENSITIVE-body-ticket');
            }
            return {};
          },
          read: () async => {'nonce': 'a' * 32},
          write: (_) async {},
          disconnect: () async {
            disconnects++;
          },
          onError: (_) {
            ended.complete();
          });
      await relay.start();
      await ended.future.timeout(const Duration(seconds: 2));
      await Future<void>.delayed(Duration.zero);
      final close = events.singleWhere((e) => e['event'] == 'relay_close');
      expect(close['phase'], 'poll');
      expect(close['http_status'], status);
      expect(close['error_type'], 'ControlHttpFailure');
      expect(close['reason'], 'error');
      expect(events.toString(), isNot(contains('SENSITIVE')));
      expect(events.toString(), isNot(contains('aaaaaaaaaaaaaaaa')));
      expect(disconnects, 1);
      await relay.close();
    });
  }
  test('uncertain read timeout is diagnosed without retry or payload',
      () async {
    final events = <Map>[];
    final ended = Completer<void>();
    var reads = 0, writes = 0;
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(SafeDiagnostics.channel, (call) async {
      if (call.method == 'diagnosticEvent') {
        events.add(Map.from(call.arguments as Map));
      }
      return null;
    });
    addTearDown(() =>
        messenger.setMockMethodCallHandler(SafeDiagnostics.channel, null));
    final relay = CloudRelay(
        post: (path, _) async => path == 'poll'
            ? {
                'state': 'action',
                'id': 'x',
                'seq': 1,
                'op': 1,
                'packet': '00' * 48
              }
            : {},
        read: () async {
          if (reads++ > 0) throw TimeoutException('SENSITIVE');
          return {'nonce': 'b' * 32};
        },
        write: (_) async {
          writes++;
        },
        disconnect: () async {},
        onError: (_) {
          ended.complete();
        });
    await relay.start();
    await ended.future.timeout(const Duration(seconds: 2));
    await Future<void>.delayed(Duration.zero);
    final close = events.singleWhere((e) => e['event'] == 'relay_close');
    expect(close['phase'], 'read');
    expect(close['op'], 1);
    expect(close['error_type'], 'TimeoutException');
    expect(writes, 1);
    expect(events.toString(), isNot(contains('SENSITIVE')));
    await relay.close();
  });
}
