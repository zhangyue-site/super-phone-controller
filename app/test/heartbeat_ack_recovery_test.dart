import 'dart:async';
import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:pcflash/cloud_relay.dart';
import 'package:pcflash/control_client.dart';
import 'gateway_recovery_flow_test.dart' as fixture;

class HeartbeatBoard extends fixture.RecoveryBoard {
  bool received = false;
  HeartbeatBoard() {
    maintenanceSupported = true;
  }
  void reconnectFresh() {
    nonce = '34' * 16;
    received = false;
  }

  @override
  Future<void> writeLocalControl(List<int> bytes) async {
    writes++;
    received = true;
  }

  @override
  Future<Map<String, dynamic>> readLocalControl() async => {
        'relayOnline': true,
        'nonce': nonce,
        'seq': received ? 1 : 0,
        'op': received ? 12 : 0,
        'result': received ? 3 : 0,
        'busy': 0,
        'hid': 0,
        'ready': 1,
      };
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  for (final op in [1, 3, 4, 6, 7, 12]) {
    test('ACK transport failure op$op reconnect eligibility: receipt-confirmed ack is recoverable',
        () async {
      var writes = 0, disconnects = 0, acks = 0;
      final ended = Completer<void>();
      final relay = CloudRelay(
        read: () async => {
          'relayOnline': true,
          'nonce': '12' * 16,
          'seq': writes == 0 ? 0 : 1,
          'op': writes == 0 ? 0 : op,
          'result': writes == 0
              ? 0
              : op == 6
                  ? 7
                  : op == 7
                      ? 8
                      : 3,
          'hid': op == 6 && writes > 0 ? 1 : 0,
          'ready': 1,
          'busy': 0,
        },
        post: (path, body) async {
          if (path == 'maintenance' || path == 'poll') {
            return {
              'state': 'action',
              'id': 'one',
              'seq': 1,
              'op': op,
              'packet': '00' * 48,
              if (op == 12) 'expiresIn': 15,
            };
          }
          if (path == 'ack') {
            acks++;
            throw http.ClientException('lost ACK response');
          }
          return {};
        },
        write: (_) async {
          writes++;
        },
        disconnect: () async {
          disconnects++;
        },
        onError: (_) {
          ended.complete();
        },
      );
      await relay.start();
      await ended.future.timeout(const Duration(seconds: 3));
      expect(relay.recoverableNetworkFailure, true, reason: 'ackrecov: 回执确认后的 ACK 失败应可恢复');
      expect(relay.closeFinished, true);
      expect(writes, 1);
      expect(acks, 1);
      expect(disconnects, 1);
      await Future<void>.delayed(const Duration(milliseconds: 250));
      expect(writes, 1,
          reason: 'a closed relay cannot replay the delivered packet');
      await relay.close();
    });
  }
  test(
      'heartbeat ACK loss recovery confirms STOP before new nonce and never replays',
      () async {
    final board = HeartbeatBoard(), calls = <String>[], nonces = <String>[];
    var delivered = false, acks = 0, authorizations = 0;
    final client = ControlClient(client: MockClient((request) async {
      final op = request.url.path.split('/').last;
      calls.add(op);
      if (op == 'authorize') authorizations++;
      if (op == 'attach') {
        final body = jsonDecode(request.body) as Map;
        nonces.add((body['receipt'] as Map)['nonce'] as String);
      }
      if (op == 'maintenance' && !delivered) {
        delivered = true;
        return http.Response(
            jsonEncode({
              'state': 'action',
              'id': 'heartbeat-one',
              'seq': 1,
              'op': 12,
              'packet': '00' * 48,
              'expiresIn': 15,
            }),
            200);
      }
      if (op == 'ack') {
        acks++;
        throw http.ClientException('lost ACK response');
      }
      if (op == 'detach') return http.Response('{}', 403);
      return http.Response(
          jsonEncode(switch (op) {
            'challenge' => {'challenge': 'a' * 64},
            'authorize' => {
                'ticket': 't' * 43,
                'expiresIn': 300,
                'scope': 'phone-commands'
              },
            'renew' => {'expiresIn': 300, 'scope': 'phone-commands'},
            'command' => {'state': 'stopped'},
            'attach' => {'state': 'connected'},
            _ => {'state': 'idle'},
          }),
          200);
    }));
    await client.authorize(board);
    await fixture.until(() => client.canRecoverGateway);
    expect(board.writes, 1);
    expect(acks, 1);
    calls.clear();
    await client.recoverGateway(
        check: () async {},
        reconnect: () async {
          calls.add('reconnect');
          board.reconnectFresh();
        });
    expect(client.authorized, true);
    expect(calls.indexOf('command'), greaterThanOrEqualTo(0));
    expect(calls.indexOf('command'), lessThan(calls.indexOf('reconnect')));
    expect(calls.indexOf('reconnect'), lessThan(calls.indexOf('attach')));
    expect(nonces, ['12' * 16, '34' * 16]);
    expect(authorizations, 1,
        reason: 'reuse valid parent grant, not a new authorization');
    expect(board.writes, 1,
        reason: 'old heartbeat and input packets are not replayed');
    expect(acks, 1);
    await client.shutdown();
  });
}
