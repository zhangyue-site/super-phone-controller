import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:pcflash/cloud_relay.dart';
import 'package:pcflash/diagnostics.dart';

void main() {
  test('one failed idle poll recovers same lease without detach or HID write',
      () async {
    var polls = 0, writes = 0, disconnects = 0;
    final errors = <Object>[];
    final relay = CloudRelay(
      post: (p, b) async {
        if (p == 'poll' && ++polls == 1) {
          throw http.ClientException('closed idle connection');
        }
        return {'state': p == 'attach' ? 'connected' : 'idle'};
      },
      read: () async => {'nonce': '12121212121212121212121212121212'},
      write: (_) async {
        writes++;
      },
      disconnect: () async {
        disconnects++;
      },
      onError: errors.add,
    );
    await relay.start();
    await Future<void>.delayed(const Duration(milliseconds: 900));
    expect(polls, greaterThanOrEqualTo(2));
    expect(relay.isClosed, isFalse);
    expect(disconnects, 0);
    expect(writes, 0);
    expect(errors, isEmpty);
    await relay.close();
  });
  test('lost poll response with server issued packet stops without replay',
      () async {
    var polls = 0, writes = 0;
    final errors = <Object>[];
    final relay = CloudRelay(
      post: (p, b) async {
        if (p == 'poll') {
          if (++polls == 1) {
            throw http.ClientException('response lost after consume');
          }
          return {'state': 'awaiting_receipt'};
        }
        return {'state': 'connected'};
      },
      read: () async => {'nonce': '12121212121212121212121212121212'},
      write: (_) async {
        writes++;
      },
      disconnect: () async {},
      onError: errors.add,
    );
    await relay.start();
    await Future<void>.delayed(const Duration(milliseconds: 900));
    expect(polls, 2);
    expect(relay.isClosed, isTrue);
    expect(writes, 0);
    expect(errors, hasLength(1));
  });
  test('lease expiry is terminal for old task and never polled again',
      () async {
    var polls = 0;
    final relay = CloudRelay(
      post: (p, b) async {
        if (p == 'poll') {
          polls++;
          throw ControlHttpFailure(409, 'lease expired',
              relayLeaseExpired: true);
        }
        return {};
      },
      read: () async => {'nonce': '12121212121212121212121212121212'},
      write: (_) async {},
      disconnect: () async {},
      onError: (_) {},
    );
    await relay.start();
    await Future<void>.delayed(const Duration(milliseconds: 900));
    expect(polls, 1);
    expect(relay.isClosed, isTrue);
  });
}
