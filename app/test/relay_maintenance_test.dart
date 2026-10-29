import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/cloud_relay.dart';

void main() {
  test('maintenance busy drains normal action before retrying heartbeat',
      () async {
    final events = <String>[];
    var writes = 0;
    final done = Completer<void>();
    final relay = CloudRelay(
      post: (path, body) async {
        events.add(path);
        if (path == 'maintenance') return {'state': 'busy'};
        if (path == 'poll') {
          return {
            'state': 'action',
            'packet': '00' * 48,
            'seq': 1,
            'op': 1,
            'id': 'normal'
          };
        }
        if (path == 'ack') {
          if (!done.isCompleted) done.complete();
          return {'state': 'acknowledged'};
        }
        return {};
      },
      read: () async => {
        'nonce': 'ab' * 16,
        'relayOnline': 0,
        'seq': 1,
        'op': 1,
        'busy': 0,
        'result': 3
      },
      write: (_) async {
        writes++;
      },
      disconnect: () async {},
      onError: (e) => fail('$e'),
    );
    await relay.start();
    await done.future.timeout(const Duration(seconds: 2));
    await relay.close();
    expect(events.take(4), ['attach', 'maintenance', 'poll', 'ack']);
    expect(writes, 1);
  });
}
