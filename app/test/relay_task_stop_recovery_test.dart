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
      var polls = 0, authorizations = 0, leaseSent = false;
      final packet = [1, 5, 1, 0, 0, 0, ...List.filled(42, 0)]
          .map((v) => v.toRadixString(16).padLeft(2, '0'))
          .join();
      final client = ControlClient(client: MockClient((request) async {
        final op = request.url.path.split('/').last;
        calls.add(op);
        if (op == 'authorize') authorizations++;
        if (op == 'poll') {
          final first = polls++ == 0;
          if (first) {
            return http.Response(
                jsonEncode({
                  'state': 'action',
                  'id': 'task-stop',
                  'seq': 1,
                  'op': 5,
                  'packet': packet
                }),
                200);
          }
          // STOP no longer closes the relay. A valid parent ticket keeps
          // polling; a lease expiry is the new terminal event that triggers
          // the full self-heal. An already-expired ticket is covered by the
          // ticket-expiry watch path instead, so do not race both triggers.
          if (!expired && !leaseSent) {
            leaseSent = true;
            return http.Response(
                jsonEncode({'code': 'relay_lease_expired'}), 409);
          }
          return http.Response(jsonEncode({'state': 'idle'}), 200);
        }
        return http.Response(
            jsonEncode(switch (op) {
              'challenge' => {'challenge': 'a' * 64},
              'authorize' => {
                  'ticket': (authorizations == 1 ? 't' : 'u') * 43,
                  'scope': 'phone-commands',
                  'expiresIn': expired && authorizations == 1 ? 1 : 300
                },
              'renew' => {'scope': 'phone-commands', 'expiresIn': 300},
              'ack' => {'state': 'acknowledged'},
              'command' => {'state': 'stopped'},
              _ => {'state': 'idle'}
            }),
            200);
      }));
      try {
        await client.authorize(board);
        await until(() => board.writes == 1);
        await Future<void>.delayed(const Duration(milliseconds: 30));
        expect(board.writes, 1, reason: 'only original STOP, never any input');
        if (!expired) {
          // Acknowledged STOP keeps the same authenticated session polling:
          // no close, no detach and no TaskRelayStopped error.
          expect(board.disconnects, 0);
          expect(client.authorized, true);
          expect(calls.where((x) => x == 'detach'), isEmpty);
          // The stopped lease then reaches the error sink and must start a
          // full challenge+authorize+attach handshake.
          await until(() => leaseSent);
        }
        // expired=true reaches the same full re-handshake through the ticket
        // expiry watch while the STOP session is still polling.
        await until(() => authorizations >= 2 && client.authorized);
        expect(client.authorized, true);
        expect(board.writes, 1, reason: 'old STOP is never replayed');
        expect(calls.where((x) => x == 'command').length, 0,
            reason:
                'ACKed STOP already reconciled the old task; preserve new queued requests');
        expect(calls.where((x) => x == 'renew'), isEmpty,
            reason: 'self-heal always re-proves capability, not renew');
        expect(calls.where((x) => x == 'challenge').length, 2);
        expect(calls.where((x) => x == 'attach').length, 2);
      } finally {
        await client.shutdown();
      }
    });
  }
}
