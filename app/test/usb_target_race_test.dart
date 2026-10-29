import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/usb_target_screen.dart';
import 'package:pcflash/usb_launch.dart';
import 'package:pcflash/screen_share.dart';

void main() {
  const serial = 'STOPTEST001';
  Map<String, dynamic> info(String value) =>
      {'protocol': 1, 'device': 'test-board', 'usbSerial': value};
  testWidgets(
      'manual stop suppresses automatic start for same serial after reenumeration',
      (tester) async {
    final initial = Completer<Map<String, dynamic>>(),
        manual = Completer<Map<String, dynamic>>();
    var identities = 0, starts = 0;
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(UsbLaunch.channel, (call) async {
      if (call.method == 'info') {
        identities++;
        return identities == 1 ? initial.future : manual.future;
      }
      return null;
    });
    messenger.setMockMethodCallHandler(ScreenShare.channel, (call) async {
      if (call.method == 'start') {
        starts++;
      }
      if (call.method == 'stop') return null;
      return '{"active":false,"capture":"未共享"}';
    });
    addTearDown(() {
      messenger.setMockMethodCallHandler(UsbLaunch.channel, null);
      messenger.setMockMethodCallHandler(ScreenShare.channel, null);
    });
    Widget screen(String session) => MaterialApp(
        home: UsbTargetScreen(
            key: ValueKey(session),
            attachment: UsbAttachment(serial, session, null, null),
            isCurrent: () => true));
    await tester.pumpWidget(screen('stop-session-1'));
    await tester.pumpAndSettle();
    expect(identities, 1);
    await tester.tap(find.text('停止控制与共享'));
    await tester.pumpAndSettle();
    await tester.pumpWidget(screen('stop-session-2'));
    await tester.pumpAndSettle();
    initial.complete(info(serial));
    await tester.pump();
    await tester.pump(const Duration(seconds: 3));
    expect(identities, 1);
    expect(starts, 0);
    await tester.scrollUntilVisible(find.text('开始屏幕共享并连接'), 200);
    await tester.drag(find.byType(ListView), const Offset(0, -200));
    await tester.pumpAndSettle();
    final button = tester.widget<FilledButton>(find.byType(FilledButton));
    expect(button.onPressed, isNotNull);
    await tester.scrollUntilVisible(find.text('开始屏幕共享并连接'), 160,
        scrollable: find.byType(Scrollable).first);
    await tester.tap(find.text('开始屏幕共享并连接'));
    await tester.pump();
    expect(identities, 2);
    await tester.pumpWidget(const SizedBox());
    manual.complete(info(serial));
    await tester.pump();
    expect(starts, 0);
    expect(tester.takeException(), isNull);
  });
  testWidgets('identity mismatch remains read-only and cannot start capture',
      (tester) async {
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    var captures = 0;
    messenger.setMockMethodCallHandler(
        UsbLaunch.channel, (_) async => info('OTHER-SERIAL'));
    messenger.setMockMethodCallHandler(ScreenShare.channel, (call) async {
      if (call.method == 'start') {
        captures++;
      }
      if (call.method == 'stop') return null;
      return '{"active":false,"capture":"未共享"}';
    });
    addTearDown(() {
      messenger.setMockMethodCallHandler(UsbLaunch.channel, null);
      messenger.setMockMethodCallHandler(ScreenShare.channel, null);
    });
    await tester.pumpWidget(MaterialApp(
        home: UsbTargetScreen(
            attachment:
                const UsbAttachment('IDENTITYTEST', 'identity-1', null, null),
            isCurrent: () => true)));
    await tester.pumpAndSettle();
    expect(find.textContaining('无法核验 USB 控制板身份'), findsOneWidget);
    expect(find.byType(TextField), findsNothing);
    expect(captures, 0);
    expect(find.text('连接控制手机'), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets('disposed pending final capture status cannot mutate or connect',
      (tester) async {
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    final finalStatus = Completer<String>();
    var statuses = 0, binds = 0;
    messenger.setMockMethodCallHandler(UsbLaunch.channel, (call) async {
      if (call.method == 'info') return info('DISPOSETEST');
      if (call.method == 'bind') {
        binds++;
      }
      return null;
    });
    messenger.setMockMethodCallHandler(ScreenShare.channel, (call) async {
      if (call.method == 'stop') return null;
      if (call.method == 'status') {
        statuses++;
        if (statuses == 3) return finalStatus.future;
        return '{"active":true,"capture":"共享中"}';
      }
      return null;
    });
    addTearDown(() {
      messenger.setMockMethodCallHandler(UsbLaunch.channel, null);
      messenger.setMockMethodCallHandler(ScreenShare.channel, null);
    });
    await tester.pumpWidget(MaterialApp(
        home: UsbTargetScreen(
            attachment:
                const UsbAttachment('DISPOSETEST', 'dispose-1', null, null),
            isCurrent: () => true)));
    await tester.pumpAndSettle();
    expect(statuses, 3);
    await tester.pumpWidget(const SizedBox());
    finalStatus.complete('{"active":true,"capture":"共享中"}');
    await tester.pumpAndSettle();
    expect(binds, 0);
    expect(tester.takeException(), isNull);
  });
  testWidgets('stop drains pending identity before allowing manual reconnect',
      (tester) async {
    final first = Completer<Map<String, dynamic>>(),
        second = Completer<Map<String, dynamic>>();
    var identities = 0;
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(UsbLaunch.channel, (call) async {
      if (call.method == 'info') {
        identities++;
        return identities == 1 ? first.future : second.future;
      }
      return null;
    });
    messenger.setMockMethodCallHandler(ScreenShare.channel, (call) async {
      if (call.method == 'stop') return null;
      return '{"active":false,"capture":"未共享"}';
    });
    addTearDown(() {
      messenger.setMockMethodCallHandler(UsbLaunch.channel, null);
      messenger.setMockMethodCallHandler(ScreenShare.channel, null);
    });
    await tester.pumpWidget(MaterialApp(
        home: UsbTargetScreen(
            attachment:
                const UsbAttachment('SAMEWIDGETTEST', 'same-1', null, null),
            isCurrent: () => true)));
    await tester.pumpAndSettle();
    await tester.tap(find.text('停止控制与共享'));
    await tester.pumpAndSettle();
    expect(find.text('正在停止…'), findsOneWidget);
    await tester.scrollUntilVisible(find.byType(FilledButton), 160,
        scrollable: find.byType(Scrollable).first);
    expect(tester.widget<FilledButton>(find.byType(FilledButton)).onPressed,
        isNull);
    first.complete(info('SAMEWIDGETTEST'));
    await tester.pumpAndSettle();
    expect(find.text('正在停止…'), findsNothing);
    await tester.drag(find.byType(ListView), const Offset(0, -250));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('开始屏幕共享并连接'), 160,
        scrollable: find.byType(Scrollable).first);
    await tester.tap(find.text('开始屏幕共享并连接'));
    await tester.pump();
    expect(identities, 2);
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.byType(FilledButton), 160,
        scrollable: find.byType(Scrollable).first);
    expect(tester.widget<FilledButton>(find.byType(FilledButton)).onPressed,
        isNull);
    expect(find.text('正在请求授权或连接…'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
    second.complete(info('SAMEWIDGETTEST'));
    await tester.pump();
    expect(tester.takeException(), isNull);
  });
}
