import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/target_session.dart';
import 'package:pcflash/screen_share.dart';
import 'package:pcflash/usb_launch.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test('opposite mode consumes old prepared hint before disconnect fallback',
      () async {
    const usb = UsbAttachment('AABBCCDDEEFF', 'AABBCCDDEEFF:1', null, null);
    final modes = <bool>[];
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(UsbLaunch.channel, (call) async {
      if (call.method == 'expectMode') {
        modes.add((call.arguments as Map)['hid'] as bool);
        return null;
      }
      return {'serial': usb.serial, 'session': usb.session};
    });
    messenger.setMockMethodCallHandler(ScreenShare.channel, (call) async {
      if (call.method == 'status') return '{"active":true}';
      final body = jsonDecode((call.arguments as Map)['body'] as String);
      return jsonEncode(body['operation'] == 'poll'
          ? {
              'state': 'prepare',
              'nonce': 'a' * 32,
              'mode': 'normal',
              'generation': 1,
              'expiresInMs': 5000
            }
          : {'state': 'ready'});
    });
    addTearDown(() {
      messenger.setMockMethodCallHandler(UsbLaunch.channel, null);
      messenger.setMockMethodCallHandler(ScreenShare.channel, null);
    });
    await TargetSession.window(usb);
    await TargetSession.modeCallback(usb)(true);
    await TargetSession.modeCallback(usb)(false);
    expect(modes, [false, true, false]);
  });
}
