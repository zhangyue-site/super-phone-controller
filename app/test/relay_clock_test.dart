import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/cloud_relay.dart';

void main() {
  test(
      'relay cadence uses supplied monotonic elapsed time instead of wall time',
      () async {
    var now = Duration.zero;
    var polls = 0, writes = 0;
    final relay = CloudRelay(
        monotonic: () => now,
        post: (p, b) async {
          if (p == 'poll') polls++;
          return {'state': p == 'attach' ? 'connected' : 'idle'};
        },
        read: () async => {'nonce': '12' * 16},
        write: (_) async {
          writes++;
        },
        disconnect: () async {},
        onError: (_) {});
    try {
      await relay.start();
      await Future<void>.delayed(const Duration(milliseconds: 650));
      expect(polls, 0);
      now = const Duration(milliseconds: 600);
      await Future<void>.delayed(const Duration(milliseconds: 150));
      expect(polls, 1);
      expect(writes, 0);
    } finally {
      await relay.close();
    }
  });
}
