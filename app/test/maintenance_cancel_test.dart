import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/cloud_relay.dart';

void main() {
  test('late maintenance receipt after close cannot ACK or resend', () async {
    final entered = Completer<void>();
    final receipt = Completer<Map<String, dynamic>>();
    var reads = 0, writes = 0, acks = 0;
    final relay = CloudRelay(
      post: (path, body) async {
        if (path == 'maintenance') {
          return {
            'state': 'action',
            'id': 'm',
            'seq': 1,
            'op': 12,
            'packet': '00' * 48,
            'expiresIn': 15
          };
        }
        if (path == 'ack') acks++;
        return {'state': 'acknowledged'};
      },
      read: () async {
        if (reads++ == 0) return {'nonce': 'ab' * 16, 'relayOnline': 0};
        entered.complete();
        return receipt.future;
      },
      write: (_) async {
        writes++;
      },
      disconnect: () async {},
      onError: (_) {},
    );
    await relay.start();
    await entered.future.timeout(const Duration(seconds: 2));
    await relay.close();
    receipt.complete(
        {'nonce': 'ab' * 16, 'seq': 1, 'op': 12, 'busy': 0, 'result': 3});
    await Future<void>.delayed(const Duration(milliseconds: 100));
    expect(writes, 1);
    expect(acks, 0);
    expect(relay.isClosed, isTrue);
  });
  for (final ttl in [null, 0, 16]) {
    test('invalid maintenance TTL $ttl never writes', () async {
      final failed = Completer<void>();
      var writes = 0;
      final relay = CloudRelay(
        post: (path, body) async => path == 'maintenance'
            ? {
                'state': 'action',
                'id': 'm',
                'seq': 1,
                'op': 12,
                'packet': '00' * 48,
                'expiresIn': ttl
              }
            : {},
        read: () async => {'nonce': 'ab' * 16, 'relayOnline': 0},
        write: (_) async {
          writes++;
        },
        disconnect: () async {},
        onError: (_) {
          failed.complete();
        },
      );
      await relay.start();
      await failed.future.timeout(const Duration(seconds: 2));
      expect(writes, 0);
      await relay.close();
    });
  }
}
