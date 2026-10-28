import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/usb_launch.dart';
import 'package:pcflash/usb_target_screen.dart';
import 'package:pcflash/screen_share.dart';

void main() {
  testWidgets(
      'unsupported USB proof stays read-only and never falls back to commands',
      (tester) async {
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    var starts = 0;
    messenger.setMockMethodCallHandler(ScreenShare.channel, (call) async {
      if (call.method == 'start') starts++;
      if (call.method == 'stop') return null;
      return '{"active":false,"capture":"未共享","task":""}';
    });
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
    expect(find.textContaining('连接未完成'), findsOneWidget);
    expect(find.text('通过蓝牙连接旧版控制板'), findsNothing);
    expect(find.byType(TextField), findsNothing);
    expect(starts, 0);
    expect(selected, 0);
    await tester.pumpWidget(const SizedBox());
  });
}
