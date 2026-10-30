import 'dart:async';
import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:pcflash/ble_ota_service.dart';
import 'package:pcflash/board_info.dart';
import 'package:pcflash/control_client.dart';
import 'package:pcflash/cloud_relay.dart';

class RecoveryBoard extends BleOtaService {
  String nonce = '12' * 16, identity = 'test-board';
  int writes = 0, proofs = 0, disconnects = 0;
  @override
  bool get supportsLocalControl => true;
  @override
  Future<BoardInfo?> readInfo() async => BoardInfo(identity, 'ci', '', '', 2);
  @override
  Future<List<int>> signDownloadChallenge(List<int> bytes) async {
    proofs++;
    return List.filled(32, 187);
  }

  @override
  Future<Map<String, dynamic>> readLocalControl() async => {
        'nonce': nonce,
        'seq': 0,
        'op': 0,
        'result': 0,
        'busy': 0,
        'hid': 0,
        'ready': 1
      };
  @override
  Future<void> writeLocalControl(List<int> bytes) async {
    writes++;
  }

  @override
  Future<void> disconnect() async {
    disconnects++;
  }
}

Future<void> until(bool Function() ready) async {
  for (var i = 0; i < 50 && !ready(); i++) {
    await Future<void>.delayed(const Duration(milliseconds: 50));
  }
  expect(ready(), true);
}

void main() {
  for (final scenario in [
    'success',
    'forbidden',
    'identity',
    'cancel',
    'expired'
  ]) {
    test(
        'recovery $scenario stops old task and never replaces parent ticket or replays',
        () async {
      final board = RecoveryBoard(), calls = <String>[], auth = <String>[];
      var firstPoll = true, authorizations = 0, attaches = 0, valid = true;
      final client = ControlClient(client: MockClient((request) async {
        final op = request.url.path.split('/').last;
        calls.add(op);
        if (request.headers['Authorization'] != null) {
          auth.add(request.headers['Authorization']!);
        }
        if (op == 'poll' && firstPoll) {
          firstPoll = false;
          throw http.ClientException('test network loss');
        }
        if (op == 'detach') return http.Response('{}', 403);
        if (op == 'renew' && scenario == 'forbidden') {
          return http.Response('{}', 403);
        }
        if (op == 'authorize') authorizations++;
        if (op == 'attach') attaches++;
        final body = switch (op) {
          'challenge' => {'challenge': 'a' * 64},
          'authorize' => {
              'ticket': 't' * 43,
              'expiresIn': scenario == 'expired' ? 1 : 300,
              'scope': 'phone-commands'
            },
          'renew' => {'expiresIn': 300, 'scope': 'phone-commands'},
          'command' => {'state': 'stopped'},
          'attach' => {'state': 'connected'},
          _ => {'state': 'idle'},
        };
        return http.Response(jsonEncode(body), 200);
      }));
      await client.authorize(board);
      await until(() => client.canRecoverGateway);
      expect(client.canReadStatus, true,
          reason: 'old lease detach403 is not parent-ticket expiry');
      calls.clear();
      if (scenario == 'expired') {
        await Future<void>.delayed(const Duration(milliseconds: 750));
      }
      Future<void> recover() => client.recoverGateway(check: () async {
            if (!valid) throw StateError('physical session ended');
          }, reconnect: () async {
            calls.add('reconnect');
            board.nonce = '34' * 16;
            if (scenario == 'identity') board.identity = 'different-board';
            if (scenario == 'cancel') {
              valid = false;
              await client.shutdown();
            }
          });
      if (scenario == 'success') {
        await recover();
        expect(client.authorized, true);
        expect(calls.indexOf('command'), lessThan(calls.indexOf('reconnect')));
        expect(calls.indexOf('renew'), lessThan(calls.indexOf('attach')));
        expect(board.proofs, 2);
        expect(attaches, 2);
      } else {
        await expectLater(recover(), throwsA(anything));
        expect(attaches, 1);
        expect(client.authorized, false);
        if (scenario == 'forbidden' || scenario == 'expired') {
          expect(client.canReadStatus, false);
        }
      }
      expect(authorizations, 1);
      expect(auth.every((value) => value == 'Bearer ${'t' * 43}'), true);
      expect(board.writes, 0);
      await client.shutdown();
    });
  }

  test('forbidden poll keeps existing denial and never auto-recovers',
      () async {
    final board = RecoveryBoard();
    final client = ControlClient(client: MockClient((request) async {
      final op = request.url.path.split('/').last;
      if (op == 'poll') return http.Response('{}', 403);
      return http.Response(
          jsonEncode(switch (op) {
            'challenge' => {'challenge': 'a' * 64},
            'authorize' => {
                'ticket': 't' * 43,
                'expiresIn': 300,
                'scope': 'phone-commands'
              },
            _ => {'state': 'connected'},
          }),
          200);
    }));
    await client.authorize(board);
    await until(() => !client.canReadStatus);
    expect(client.canRecoverGateway, false);
    expect(client.authorized, false);
    expect(board.writes, 0);
    await client.shutdown();
  });
  test('unknown ACK network error cannot opt into automatic recovery',
      () async {
    var writes = 0, disconnects = 0;
    final stopped = Completer<void>();
    final events = <String>[];
    final relay = CloudRelay(
        read: () async => {
              'nonce': '12' * 16,
              'seq': writes,
              'op': writes == 0 ? 0 : 1,
              'result': writes == 0 ? 0 : 3,
              'busy': 0,
              'hid': writes,
              'ready': 1
            },
        write: (_) async {
          writes++;
        },
        post: (op, body) async {
          if (op == 'poll') {
            return {
              'state': 'action',
              'id': 'action',
              'seq': 1,
              'op': 1,
              'packet': '00' * 48
            };
          }
          if (op == 'ack') throw http.ClientException('unknown ack outcome');
          return {'state': 'connected'};
        },
        beforeModeChange: (hid) async {
          events.add('prepare:$hid');
        },
        disconnect: () async {
          events.add('disconnect');
          disconnects++;
        },
        onError: (_) {
          stopped.complete();
        });
    await relay.start();
    await stopped.future.timeout(const Duration(seconds: 3));
    expect(writes, 1);
    expect(disconnects, 1);
    expect(relay.recoverableNetworkFailure, false);
    expect(events, ['prepare:false', 'disconnect']);
  });
  test('fresh connection rejects retired nonce before attach or writes',
      () async {
    var posts = 0, writes = 0;
    final relay = CloudRelay(
        retiredNonce: '12' * 16,
        read: () async => {'nonce': '12' * 16},
        post: (_, body) async {
          posts++;
          return {};
        },
        write: (_) async {
          writes++;
        },
        disconnect: () async {},
        onError: (_) {});
    await expectLater(relay.start(), throwsFormatException);
    expect(posts, 0);
    expect(writes, 0);
  });
}
