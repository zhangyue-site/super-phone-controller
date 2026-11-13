import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:pcflash/control_client.dart';
import 'gateway_recovery_flow_test.dart' show RecoveryBoard, until;

class StopBoard extends RecoveryBoard {
  int seq = 0, op = 0;
  @override
  Future<void> writeLocalControl(List<int> packet) async {
    writes++;
    op = packet[1];
    seq = packet[2] | packet[3] << 8 | packet[4] << 16 | packet[5] << 24;
  }

  @override
  Future<Map<String, dynamic>> readLocalControl() async => {
        'nonce': nonce,
        'seq': seq,
        'op': op,
        'result': op == 5 ? 5 : 0,
        'hid': 0,
        'busy': 0,
        'ready': 1
      };
  void reconnect() {
    nonce = '34' * 16;
    seq = 0;
    op = 0;
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  for (final expired in [false, true]) {
    test(
        'acknowledged task STOP recovers passive gateway with expired=$expired',
        () async {
      final board = StopBoard(), calls = <String>[];
      var polls = 0, authorizations = 0;
      final packet = [1, 5, 1, 0, 0, 0, ...List.filled(42, 0)]
          .map((v) => v.toRadixString(16).padLeft(2, '0'))
          .join();
      final client = ControlClient(client: MockClient((request) async {
        final op = request.url.path.split('/').last;
        calls.add(op);
        if (op == 'authorize') authorizations++;
        return http.Response(
            jsonEncode(switch (op) {
              'challenge' => {'challenge': 'a' * 64},
              'authorize' => {
                  'ticket': (authorizations == 1 ? 't' : 'u') * 43,
                  'scope': 'phone-commands',
                  'expiresIn': expired && authorizations == 1 ? 1 : 300
                },
              'renew' => {'scope': 'phone-commands', 'expiresIn': 300},
              'poll' => polls++ == 0
                  ? {
                      'state': 'action',
                      'id': 'task-stop',
                      'seq': 1,
                      'op': 5,
                      'packet': packet
                    }
                  : {'state': 'idle'},
              'ack' => {'state': 'acknowledged'},
              'command' => {'state': 'stopped'},
              _ => {'state': 'idle'}
            }),
            200);
      }));
      try {
        await client.authorize(board);
        await until(() => board.disconnects > 0);
        await Future<void>.delayed(const Duration(milliseconds: 30));
        expect(board.writes, 1, reason: 'only original STOP, never any input');
        if (expired) {
          await Future<void>.delayed(const Duration(milliseconds: 650));
          expect(client.canReadStatus, false);
        }
        expect(client.canRecoverGateway, true,
            reason:
                'stopped input authority must not kill passive future-task transport');
        await client.recoverGateway(
            check: () async {},
            reconnect: () async {
              calls.add('fresh-nonce');
              board.reconnect();
            });
        expect(client.authorized, true);
        expect(board.writes, 1);
        expect(calls.where((x) => x == 'command').length, 0,
            reason:
                'ACKed STOP already reconciled the old task; preserve new queued requests');
        expect(calls.where((x) => x == 'detach').length, 0);
        if (expired) {
          expect(authorizations, 2);
          expect(calls.lastIndexOf('authorize'),
              lessThan(calls.lastIndexOf('attach')));
        } else {
          expect(authorizations, 1);
          expect(calls.indexOf('fresh-nonce'),
              lessThan(calls.lastIndexOf('attach')));
        }
      } finally {
        await client.shutdown();
      }
    });
  }
}
