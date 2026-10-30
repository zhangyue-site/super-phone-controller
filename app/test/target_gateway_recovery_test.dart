import 'dart:async';
import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:pcflash/control_client.dart';
import 'package:pcflash/target_session.dart';
import 'package:pcflash/screen_share.dart';
import 'package:pcflash/usb_launch.dart';
import 'gateway_recovery_flow_test.dart' show RecoveryBoard, until;

class BoundBoard extends RecoveryBoard {
  final connected = <String>[];
  Completer<void>? pendingConnect;
  @override
  Future<int> connect(BluetoothDevice device) async {
    connected.add(device.remoteId.str);
    await pendingConnect?.future;
    nonce = '34' * 16;
    return 20;
  }

  @override
  Future<void> startScan() async =>
      throw StateError('automatic recovery must never scan');
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  for (final scenario in [
    'fixed-device',
    'projection-stopped',
    'usb-replaced',
    'released',
    'late-stop'
  ]) {
    test(
        'app-owned recovery $scenario respects physical owner and singleflight',
        () async {
      final messenger =
          TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
      const usb = UsbAttachment(
          'AABBCCDDEEFF', 'AABBCCDDEEFF:1', 'AA:BB:CC:DD:EE:01', 'test-board');
      var active = true,
          serial = usb.serial,
          session = usb.session,
          firstPoll = true,
          requests = 0;
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
      final board = BoundBoard();
      final client = ControlClient(client: MockClient((request) async {
        final op = request.url.path.split('/').last;
        if (op == 'poll' && firstPoll) {
          firstPoll = false;
          throw http.ClientException('transient transport');
        }
        if (op == 'command') requests++;
        return http.Response(
            jsonEncode(switch (op) {
              'challenge' => {'challenge': 'a' * 64},
              'authorize' => {
                  'ticket': 't' * 43,
                  'scope': 'phone-commands',
                  'expiresIn': 300
                },
              'renew' => {'scope': 'phone-commands', 'expiresIn': 300},
              'command' => {'state': 'stopped'},
              _ => {'state': 'idle'}
            }),
            200);
      }));
      await client.authorize(board);
      TargetSession.retain(usb, client, board);
      if (scenario == 'fixed-device') {
        // Returning to a healthy target page must not disable later recovery.
        await TargetSession.cancelRecovery();
        TargetSession.resumeRecovery(client);
      }
      await until(() => client.canRecoverGateway);
      expect(await TargetSession.maintainGateway(usb), false);
      if (scenario == 'projection-stopped') active = false;
      if (scenario == 'usb-replaced') {
        serial = '112233445566';
        session = '112233445566:2';
      }
      if (scenario == 'released') await TargetSession.release();
      if (scenario == 'late-stop') board.pendingConnect = Completer<void>();
      await Future<void>.delayed(const Duration(milliseconds: 2100));
      final a = TargetSession.maintainGateway(usb);
      final b = TargetSession.maintainGateway(usb);
      if (scenario == 'late-stop') {
        await until(() => board.connected.isNotEmpty);
        final released = TargetSession.release();
        board.pendingConnect!.complete();
        expect(await a, false);
        expect(await b, false);
        await released;
        expect(client.authorized, false);
      } else {
        final results = await Future.wait([a, b]);
        if (scenario == 'fixed-device') {
          expect(results, [true, true]);
          expect(board.connected, [usb.remoteId]);
          expect(requests, 1);
          expect(client.authorized, true);
        } else {
          expect(results, [false, false]);
          expect(board.connected, isEmpty);
          expect(requests, 0);
        }
      }
      await TargetSession.release();
      messenger.setMockMethodCallHandler(UsbLaunch.channel, null);
      messenger.setMockMethodCallHandler(ScreenShare.channel, null);
    });
  }
}
