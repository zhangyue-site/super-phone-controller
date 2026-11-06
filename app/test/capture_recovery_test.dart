import 'dart:convert';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:pcflash/screen_share.dart';
import 'package:pcflash/usb_launch.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  for (final race in ['normal', 'stopped', 'native-replaced']) {
    test('recover same projection via USB with race $race', () async {
      final calls = <String>[];
      var valid = true, revoked = 0;
      final messenger =
          TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
      messenger.setMockMethodCallHandler(ScreenShare.channel, (call) async {
        calls.add(call.method);
        if (call.method == 'captureSession') {
          return {
            'generation': 7,
            'serial': 'AABBCCDDEEFF',
            'needsAuthorization': true
          };
        }
        if (call.method == 'replaceUsbCapture') {
          expect(call.arguments['generation'], 7);
          expect(call.arguments['serial'], 'AABBCCDDEEFF');
          if (race == 'native-replaced') {
            throw PlatformException(code: 'capture_session_invalid');
          }
          return null;
        }
        fail('Recovery must not invoke MediaProjection start/consent');
      });
      messenger.setMockMethodCallHandler(
          UsbLaunch.channel,
          (call) async => call.method == 'info'
              ? {'protocol': 1, 'device': 'board', 'usbSerial': 'AABBCCDDEEFF'}
              : {
                  'device': 'board',
                  'usbSerial': 'AABBCCDDEEFF',
                  'proof': 'b' * 64
                });
      addTearDown(() {
        messenger.setMockMethodCallHandler(ScreenShare.channel, null);
        messenger.setMockMethodCallHandler(UsbLaunch.channel, null);
      });
      final client = MockClient((request) async {
        if (request.url.path.endsWith('/usb-challenge')) {
          return http.Response(jsonEncode({'challenge': 'a' * 64}), 200);
        }
        if (request.url.path.endsWith('/usb-authorize')) {
          if (race == 'stopped') valid = false;
          return http.Response(
              jsonEncode({
                'ticket': 't' * 43,
                'scope': 'screen-frames',
                'expiresIn': 300
              }),
              200);
        }
        if (request.url.path.endsWith('/stop')) {
          revoked++;
          return http.Response('{}', 200);
        }
        fail('unexpected HTTP endpoint');
      });
      final future = ScreenShare.recoverUsb(
          const UsbAttachment('AABBCCDDEEFF', 'physical-session', null, null),
          client: client,
          isCurrent: () => valid);
      if (race == 'normal') {
        expect(await future, isTrue);
        expect(calls, ['captureSession', 'replaceUsbCapture']);
        expect(revoked, 0);
      } else {
        await expectLater(future, throwsA(anything));
        expect(revoked, 1);
        if (race == 'stopped') expect(calls, ['captureSession']);
      }
    });
  }
  test('valid cloud ticket needs no new USB authentication or projection start',
      () async {
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(
        ScreenShare.channel,
        (_) async => {
              'generation': 8,
              'serial': 'AABBCCDDEEFF',
              'needsAuthorization': false
            });
    addTearDown(
        () => messenger.setMockMethodCallHandler(ScreenShare.channel, null));
    expect(
        await ScreenShare.recoverUsb(
            const UsbAttachment('AABBCCDDEEFF', 's', null, null),
            client: MockClient((_) async {
          fail('No HTTP expected');
        })),
        isFalse);
  });
}
