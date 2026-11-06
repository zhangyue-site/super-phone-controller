import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/cloud_relay.dart';

void main() {
  for (final op in [8, 9, 10, 13, 14]) {
    test('signed opaque keyboard op $op obeys allowlist and one write',
        () async {
      var writes = 0, acks = 0;
      final ended = Completer<void>();
      final relay = CloudRelay(
        post: (path, body) async {
          if (path == 'poll') {
            return {
              'state': 'action',
              'id': 'keyboard',
              'seq': 1,
              'op': op,
              'packet': 'ab' * 48
            };
          }
          if (path == 'ack') {
            acks++;
            ended.complete();
            return {'state': 'acknowledged'};
          }
          return {};
        },
        read: () async =>
            {'nonce': 'ab' * 16, 'seq': 1, 'op': op, 'busy': 0, 'result': 3},
        write: (bytes) async {
          expect(bytes, List.filled(48, 0xab));
          writes++;
        },
        disconnect: () async {},
        onError: (_) {
          if (!ended.isCompleted) ended.complete();
        },
      );
      await relay.start();
      await ended.future.timeout(const Duration(seconds: 2));
      await relay.close();
      expect(writes, op >= 13 ? 1 : 0);
      expect(acks, op >= 13 ? 1 : 0);
    });
  }
}
