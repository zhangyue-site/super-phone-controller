import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/usb_launch.dart';
import 'package:pcflash/usb_target_screen.dart';
import 'package:pcflash/screen_share.dart';

void main() {
  testWidgets(
      'unsupported USB proof exposes explicit legacy entry only after failure',
      (tester) async {
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(ScreenShare.channel,
        (call) async => '{"active":false,"capture":"未共享","task":""}');
    messenger.setMockMethodCallHandler(UsbLaunch.channel,
        (call) async => throw PlatformException(code: 'usb_proof_failed'));
    addTearDown(() {
      messenger.setMockMethodCallHandler(ScreenShare.channel, null);
      messenger.setMockMethodCallHandler(UsbLaunch.channel, null);
    });
    var selected = 0;
    await tester.pumpWidget(MaterialApp(
        home: UsbTargetScreen(
            attachment: const UsbAttachment(
                'AABBCCDDEEFF', 'AABBCCDDEEFF:1', null, null),
            isCurrent: () => true,
            onLegacy: () {
              selected++;
            })));
    await tester.pumpAndSettle();
    expect(find.text('通过蓝牙连接旧版控制板'), findsOneWidget);
    expect(selected, 0);
    await tester.tap(find.text('通过蓝牙连接旧版控制板'));
    expect(selected, 1);
    await tester.pumpWidget(const SizedBox());
  });
}
