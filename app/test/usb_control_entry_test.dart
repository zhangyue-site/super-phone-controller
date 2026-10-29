import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/screen_share.dart';
import 'package:pcflash/usb_launch.dart';
import 'package:pcflash/usb_target_screen.dart';

void main() {
  testWidgets('target retains active capture and never routes to command entry',
      (tester) async {
    var selected = 0, starts = 0, stops = 0;
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(ScreenShare.channel, (call) async {
      if (call.method == 'start') {
        starts++;
        return null;
      }
      if (call.method == 'stop') {
        stops++;
        return null;
      }
      return '{"active":true,"capture":"共享中","task":""}';
    });
    messenger.setMockMethodCallHandler(
        UsbLaunch.channel,
        (call) async => {
              'protocol': 1,
              'usbSerial': 'AABBCCDDEEFF',
              'device': 'test-board'
            });
    addTearDown(() {
      messenger.setMockMethodCallHandler(ScreenShare.channel, null);
      messenger.setMockMethodCallHandler(UsbLaunch.channel, null);
    });
    await tester.pumpWidget(MaterialApp(
        home: UsbTargetScreen(
            attachment:
                const UsbAttachment('AABBCCDDEEFF', 'session', null, null),
            isCurrent: () => true,
            onLegacy: () => selected++)));
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    expect(find.text('被控手机'), findsOneWidget);
    expect(find.byType(TextField), findsNothing);
    expect(starts, 0);
    expect(stops, 0);
    expect(selected, 0);
    await tester.pumpWidget(const SizedBox());
    await tester.pump();
    expect(stops, 0); // Page disposal only removes observation.
  });
}
