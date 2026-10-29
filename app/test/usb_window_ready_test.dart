import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/screen_share.dart';
import 'package:pcflash/usb_launch.dart';
import 'package:pcflash/usb_target_screen.dart';

void main() {
  testWidgets(
      'second ready poll waits for A without duplicate mode preparation',
      (tester) async {
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    var prepared = false, expects = 0, readyRequests = 0, polls = 0;
    messenger.setMockMethodCallHandler(ScreenShare.channel, (call) async {
      if (call.method == 'usbWindow') {
        final body = jsonDecode(call.arguments['body'] as String) as Map;
        if (body['operation'] == 'ready') {
          readyRequests++;
          prepared = true;
          return '{"state":"ready"}';
        }
        polls++;
        return jsonEncode(prepared
            ? {'state': 'ready'}
            : {
                'state': 'prepare',
                'nonce': 'ab' * 16,
                'mode': 'hid',
                'generation': 1,
                'expiresInMs': 1
              });
      }
      if (call.method == 'status') {
        return '{"active":true,"capture":"共享中","task":""}';
      }
      return null;
    });
    messenger.setMockMethodCallHandler(UsbLaunch.channel, (call) async {
      if (call.method == 'expectMode') {
        expects++;
        return null;
      }
      return {'protocol': 1, 'usbSerial': '112233445566', 'device': 'board'};
    });
    addTearDown(() {
      messenger.setMockMethodCallHandler(ScreenShare.channel, null);
      messenger.setMockMethodCallHandler(UsbLaunch.channel, null);
    });
    await tester.pumpWidget(MaterialApp(
        home: UsbTargetScreen(
            attachment: const UsbAttachment(
                '112233445566', 'session-ready', null, null),
            isCurrent: () => true)));
    await tester.pumpAndSettle();
    await tester.pump(const Duration(seconds: 2));
    await tester.pumpAndSettle();
    await tester.pump(const Duration(seconds: 2));
    await tester.pumpAndSettle();
    expect(polls, greaterThanOrEqualTo(2));
    expect(expects, 1);
    expect(readyRequests, 1);
    expect(find.textContaining('USB切换窗口无效'), findsNothing);
    expect(find.textContaining('状态检查失败'), findsNothing);
    await tester.pumpWidget(const SizedBox());
    await tester.pump();
  });
}
