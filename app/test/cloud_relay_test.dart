import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/cloud_relay.dart';

void main() {
  test('one ATT write even when cloud ACK fails; disconnects', () async {
    var writes = 0, disconnected = 0;
    final events = <String>[];
    final relay = CloudRelay(
      post: (p, b) async {
        events.add(p);
        if (p == 'attach') return {'state': 'connected'};
        if (p == 'poll') {
          return {
            'state': 'action',
            'id': 'action',
            'seq': 1,
            'op': 1,
            'packet': List.filled(96, '0').join()
          };
        }
        if (p == 'ack') throw TimeoutException('lost response');
        return {'state': 'stopped'};
      },
      read: () async => {
        'nonce': '12121212121212121212121212121212',
        'seq': 1,
        'op': 1,
        'result': 3,
        'busy': 0
      },
      write: (b) async {
        writes++;
      },
      disconnect: () async {
        disconnected++;
      },
      onError: (e) {
        events.add('error');
      },
    );
    await relay.start();
    await Future<void>.delayed(const Duration(milliseconds: 1200));
    expect(writes, 1);
    expect(disconnected, 1);
    expect(events, contains('error'));
    await relay.close();
    expect(relay.isClosed, true);
    await expectLater(relay.start(), throwsStateError);
  });
  test('nonce change after dispatch closes connection without second write',
      () async {
    var reads = 0, writes = 0, disconnected = 0;
    final relay = CloudRelay(
      post: (p, b) async => p == 'poll'
          ? {
              'state': 'action',
              'id': 'x',
              'seq': 1,
              'op': 1,
              'packet': List.filled(96, '0').join()
            }
          : {},
      read: () async => {
        'nonce': reads++ == 0
            ? '12121212121212121212121212121212'
            : '34343434343434343434343434343434'
      },
      write: (b) async {
        writes++;
      },
      disconnect: () async {
        disconnected++;
      },
      onError: (_) {},
    );
    await relay.start();
    await Future<void>.delayed(const Duration(milliseconds: 1200));
    expect(writes, 1);
    expect(disconnected, 1);
  });
}
