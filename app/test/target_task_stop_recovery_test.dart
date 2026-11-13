import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:pcflash/control_client.dart';
import 'package:pcflash/target_session.dart';
import 'package:pcflash/screen_share.dart';
import 'package:pcflash/usb_launch.dart';
import 'relay_task_stop_recovery_test.dart' show StopBoard;
import 'gateway_recovery_flow_test.dart' show until;

class BoundStopBoard extends StopBoard {
  int connections = 0;
  @override
  Future<int> connect(BluetoothDevice device) async {
    connections++;
    reconnect();
    return 20;
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  for (final scenario in [
    'active',
    'projection-stopped',
    'usb-replaced',
    'released'
  ]) {
    test(
        'task STOP passive recovery requires live same USB and projection: $scenario',
        () async {
      final messenger =
          TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
      const usb = UsbAttachment(
          'AABBCCDDEEFF', 'AABBCCDDEEFF:1', 'AA:BB:CC:DD:EE:01', 'test-board');
      var active = true, session = usb.session, serial = usb.serial, polls = 0;
      messenger.setMockMethodCallHandler(
          UsbLaunch.channel,
          (_) async => {
                'serial': serial,
                'session': session,
                'remoteId': usb.remoteId,
                'deviceId': usb.deviceId
              });
      messenger.setMockMethodCallHandler(
          ScreenShare.channel, (_) async => jsonEncode({'active': active}));
      final board = BoundStopBoard(), operations = <String>[];
      final packet = [1, 5, 1, 0, 0, 0, ...List.filled(42, 0)]
          .map((v) => v.toRadixString(16).padLeft(2, '0'))
          .join();
      final client = ControlClient(client: MockClient((request) async {
        final op = request.url.path.split('/').last;
        operations.add(op);
        return http.Response(
            jsonEncode(switch (op) {
              'challenge' => {'challenge': 'a' * 64},
              'authorize' => {
                  'ticket': 't' * 43,
                  'scope': 'phone-commands',
                  'expiresIn': 300
                },
              'renew' => {'scope': 'phone-commands', 'expiresIn': 300},
              'poll' => polls++ == 0
                  ? {
                      'state': 'action',
                      'id': 'stop',
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
        TargetSession.retain(usb, client, board);
        await until(() => board.disconnects > 0);
        await Future<void>.delayed(const Duration(milliseconds: 30));
        expect(client.canRecoverStoppedTask, true);
        expect(await TargetSession.maintainGateway(usb), false);
        if (scenario == 'projection-stopped') active = false;
        if (scenario == 'usb-replaced') {
          serial = '112233445566';
          session = '112233445566:2';
        }
        if (scenario == 'released') await TargetSession.release();
        await Future<void>.delayed(const Duration(milliseconds: 2100));
        final recovered = await TargetSession.maintainGateway(usb);
        expect(recovered, scenario == 'active');
        expect(board.connections, scenario == 'active' ? 1 : 0);
        expect(board.writes, 1,
            reason: 'only old STOP, no input or ARM replay');
        if (scenario == 'active') {
          expect(client.authorized, true);
          expect(operations.where((x) => x == 'command'), isEmpty);
          expect(operations.where((x) => x == 'detach'), isEmpty);
        }
      } finally {
        await TargetSession.release();
        await client.shutdown();
        messenger.setMockMethodCallHandler(UsbLaunch.channel, null);
        messenger.setMockMethodCallHandler(ScreenShare.channel, null);
      }
    });
  }
}
