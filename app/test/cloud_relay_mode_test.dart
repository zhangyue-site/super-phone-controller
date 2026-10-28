import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/cloud_relay.dart';

void main() {
  for (final op in [6, 7, 5]) {
    test('mode hook for op $op completes before a single ATT write', () async {
      final entered = Completer<void>(),
          release = Completer<void>(),
          acked = Completer<void>();
      final events = <String>[];
      var writes = 0;
      final relay = CloudRelay(
        post: (path, _) async {
          if (path == 'poll') {
            return {
              'state': 'action',
              'id': 'mode',
              'seq': 1,
              'op': op,
              'packet': '01' * 48
            };
          }
          if (path == 'ack') {
            events.add('ack');
            acked.complete();
            return {'state': 'acknowledged'};
          }
          return {};
        },
        read: () async => {
          'nonce': '12' * 16,
          'seq': writes,
          'op': op,
          'busy': 0,
          'result': op == 6
              ? 7
              : op == 7
                  ? 8
                  : 5,
          'ready': 1,
          'hid': op == 6 ? 1 : 0
        },
        beforeModeChange: (hid) async {
          expect(hid, op == 6);
          events.add('hook');
          entered.complete();
          await release.future;
          events.add('guard-ready');
        },
        write: (bytes) async {
          expect(bytes, List.filled(48, 1));
          writes++;
          events.add('write');
        },
        disconnect: () async {},
        onError: (e) => fail('unexpected error: $e'),
      );
      addTearDown(relay.close);
      await relay.start();
      await entered.future.timeout(const Duration(seconds: 3));
      expect(writes, 0);
      expect(events, ['hook']);
      release.complete();
      await acked.future.timeout(const Duration(seconds: 3));
      expect(writes, 1);
      expect(events, ['hook', 'guard-ready', 'write', 'ack']);
      await relay.close();
    });
    test('mode hook failure for op $op disconnects without ATT write',
        () async {
      final failed = Completer<void>();
      var writes = 0, disconnects = 0, hooks = 0;
      final relay = CloudRelay(
        post: (path, _) async => path == 'poll'
            ? {
                'state': 'action',
                'id': 'mode',
                'seq': 1,
                'op': op,
                'packet': '01' * 48
              }
            : {},
        read: () async => {'nonce': '12' * 16},
        beforeModeChange: (_) async {
          hooks++;
          throw StateError('native guard failed');
        },
        write: (_) async {
          writes++;
        },
        disconnect: () async {
          disconnects++;
        },
        onError: (_) {
          failed.complete();
        },
      );
      addTearDown(relay.close);
      await relay.start();
      await failed.future.timeout(const Duration(seconds: 3));
      expect(hooks, 1);
      expect(writes, 0);
      expect(disconnects, 1);
      expect(relay.isClosed, isTrue);
    });
  }
  test('invalid signed packet shape is rejected before native mode hook',
      () async {
    final failed = Completer<void>();
    var writes = 0, hooks = 0, disconnects = 0;
    final relay = CloudRelay(
      post: (path, _) async => path == 'poll'
          ? {'state': 'action', 'seq': 1, 'op': 6, 'packet': 'invalid'}
          : {},
      read: () async => {'nonce': '12' * 16},
      beforeModeChange: (_) async {
        hooks++;
      },
      write: (_) async {
        writes++;
      },
      disconnect: () async {
        disconnects++;
      },
      onError: (_) {
        failed.complete();
      },
    );
    addTearDown(relay.close);
    await relay.start();
    await failed.future.timeout(const Duration(seconds: 3));
    expect(hooks, 0);
    expect(writes, 0);
    expect(disconnects, 1);
  });
}
