import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/screen_share.dart';
import 'package:pcflash/usb_launch.dart';
import 'package:pcflash/usb_target_screen.dart';

void main() {
  testWidgets(
      'only proven same-generation capture recovery clears startup capture error',
      (tester) async {
    tester.view.physicalSize = const Size(1000, 2400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    const serial = 'AABBCCDDEE77';
    var fail = true;
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(
        UsbLaunch.channel,
        (call) async =>
            {'protocol': 1, 'device': 'test-board', 'usbSerial': serial});
    messenger.setMockMethodCallHandler(ScreenShare.channel, (call) async {
      if (call.method == 'status') {
        return jsonEncode({'active': true, 'capture': '共享中', 'task': ''});
      }
      if (call.method == 'captureSession') {
        return {'serial': serial, 'generation': 1, 'needsAuthorization': false};
      }
      if (call.method == 'usbWindow') return '{"state":"ready"}';
      return null;
    });
    addTearDown(() {
      messenger.setMockMethodCallHandler(UsbLaunch.channel, null);
      messenger.setMockMethodCallHandler(ScreenShare.channel, null);
    });
    await tester.pumpWidget(MaterialApp(
        home: UsbTargetScreen(
            attachment: const UsbAttachment(
                serial, 'AABBCCDDEE77:startup-recovery', null, null),
            isCurrent: () => true,
            renewCapture: (_) async {
              if (fail) throw StateError('capture-start-failed');
            })));
    await tester.pumpAndSettle();
    expect(find.textContaining('capture-start-failed'), findsOneWidget);
    await tester.pump(const Duration(seconds: 2));
    await tester.pumpAndSettle();
    expect(find.textContaining('连接未完成：'), findsOneWidget,
        reason: 'active screenshot alone is not credential recovery');
    fail = false;
    await tester.pump(const Duration(seconds: 2));
    await tester.pumpAndSettle();
    expect(find.textContaining('capture-start-failed'), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });
}
