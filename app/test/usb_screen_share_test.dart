import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:pcflash/screen_share.dart';
import 'package:pcflash/usb_launch.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const usb = UsbAttachment('AABBCCDDEEFF', 'AABBCCDDEEFF:2', null, null);
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  for (final mode in [
    'valid',
    'wrong-serial',
    'cancel-grant',
    'cancel-start'
  ]) {
    test(
        'USB authorization $mode enforces identity and revokes cancelled ticket',
        () async {
      var current = true;
      final calls = <String>[];
      messenger.setMockMethodCallHandler(UsbLaunch.channel, (call) async {
        calls.add(call.method);
        expect(call.arguments['session'], usb.session);
        if (call.method == 'info') {
          return {
            'protocol': 1,
            'device': 'board-1',
            'version': '1',
            'usbSerial': usb.serial
          };
        }
        expect(call.method, 'sign');
        expect(call.arguments['nonce'], 'a' * 64);
        return {
          'device': 'board-1',
          'usbSerial': mode == 'wrong-serial' ? '001122334455' : usb.serial,
          'proof': 'b' * 64
        };
      });
      messenger.setMockMethodCallHandler(ScreenShare.channel, (call) async {
        calls.add(call.method);
        if (call.method == 'start') {
          expect(call.arguments['usbSession'], usb.session);
          if (mode == 'cancel-start') current = false;
        }
        return null;
      });
      final client = MockClient((request) async {
        final path = request.url.path.split('/').last;
        calls.add(path);
        if (path == 'stop') {
          expect(request.headers['Authorization'], 'Bearer ${'t' * 43}');
          return http.Response('{}', 200);
        }
        final body = jsonDecode(request.body) as Map;
        expect(body['device'], 'board-1');
        expect(body['serial'], usb.serial);
        if (path == 'usb-challenge') {
          return http.Response(jsonEncode({'challenge': 'a' * 64}), 200);
        }
        expect(path, 'usb-authorize');
        expect(body['proof'], 'b' * 64);
        if (mode == 'cancel-grant') current = false;
        return http.Response(
            jsonEncode({'scope': 'screen-frames', 'ticket': 't' * 43}), 200);
      });
      addTearDown(() {
        client.close();
        messenger.setMockMethodCallHandler(UsbLaunch.channel, null);
        messenger.setMockMethodCallHandler(ScreenShare.channel, null);
      });
      final future =
          ScreenShare.startUsb(usb, client: client, isCurrent: () => current);
      if (mode == 'valid') {
        await future;
        expect(
            calls, ['info', 'usb-challenge', 'sign', 'usb-authorize', 'start']);
      } else {
        await expectLater(future, throwsA(anything));
        if (mode == 'wrong-serial') {
          expect(calls, ['info', 'usb-challenge', 'sign']);
        } else {
          expect(calls.last, 'stop');
          if (mode == 'cancel-grant') expect(calls, isNot(contains('start')));
        }
      }
    });
  }
}
