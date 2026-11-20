import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:pcflash/control_client.dart';
import 'package:pcflash/target_session.dart';
import 'package:pcflash/usb_launch.dart';
import 'relay_task_stop_recovery_test.dart' show StopBoard;
import 'gateway_recovery_flow_test.dart' show until;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test(
      'task STOP keeps passive polling and a later lease expiry self-heals once',
      () async {
    const usb = UsbAttachment(
        'AABBCCDDEEFF', 'AABBCCDDEEFF:1', 'AA:BB:CC:DD:EE:01', 'test-board');
    final board = StopBoard(), operations = <String>[];
    var polls = 0, authorizations = 0, leaseSent = false;
    final packet = [1, 5, 1, 0, 0, 0, ...List.filled(42, 0)]
        .map((v) => v.toRadixString(16).padLeft(2, '0'))
        .join();
    final client = ControlClient(client: MockClient((request) async {
      final op = request.url.path.split('/').last;
      operations.add(op);
      if (op == 'authorize') authorizations++;
      if (op == 'poll') {
        if (polls++ == 0) {
          return http.Response(
              jsonEncode({
                'state': 'action',
                'id': 'stop',
                'seq': 1,
                'op': 5,
                'packet': packet
              }),
              200);
        }
        if (!leaseSent) {
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
                'expiresIn': 300
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
      TargetSession.retain(usb, client, board);
      await until(() => board.writes == 1);
      // STOP itself no longer produces a closed relay, so the app-owned
      // recovery gate has nothing to claim while the same session polls.
      expect(client.canRecoverStoppedTask, true);
      expect(await TargetSession.maintainGateway(usb), false);
      expect(board.disconnects, 0);
      // The stopped lease is the new terminal event: it must trigger exactly
      // one full relay self-heal, not duplicate app-owned recovery.
      await until(() => leaseSent && authorizations >= 2 && client.authorized);
      expect(authorizations, 2);
      expect(board.writes, 1, reason: 'only old STOP, no input or ARM replay');
      expect(board.disconnects, 1);
      expect(client.authorized, true);
      expect(operations.where((x) => x == 'command'), isEmpty);
      expect(operations.where((x) => x == 'renew'), isEmpty);
    } finally {
      await TargetSession.release();
      await client.shutdown();
    }
  });
}
