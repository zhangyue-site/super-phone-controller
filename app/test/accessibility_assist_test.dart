import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/accessibility_assist.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('pcflash/accessibility');
  var enabled = false, connected = false;
  var calls = <String>[];
  setUp(() {
    enabled = false;
    connected = false;
    calls = [];
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
      calls.add(call.method);
      if (call.method == 'setEnabled') {
        enabled = (call.arguments as Map)['enabled'] == true;
      }
      return {
        'enabled': enabled,
        'connected': connected,
        'captureActive': true
      };
    });
  });
  tearDown(() => TestDefaultBinaryMessengerBinding
      .instance.defaultBinaryMessenger
      .setMockMethodCallHandler(channel, null));
  testWidgets(
      'opt-in is separate from system connection and opening settings is explicit',
      (tester) async {
    await tester.pumpWidget(
        const MaterialApp(home: Scaffold(body: AccessibilityAssistCard())));
    await tester.pumpAndSettle();
    expect(find.text('无障碍辅助定位'), findsOneWidget);
    expect(calls, contains('status'));
    expect(calls, isNot(contains('openSettings')));
    await tester.tap(find.byType(SwitchListTile));
    await tester.pumpAndSettle();
    expect(enabled, isTrue);
    expect(find.textContaining('等待系统开启'), findsOneWidget);
    await tester.ensureVisible(find.text('前往系统设置'));
    await tester.tap(find.text('前往系统设置'));
    await tester.pumpAndSettle();
    expect(calls, contains('openSettings'));
    connected = true;
    await tester.pump(const Duration(seconds: 2));
    await tester.pumpAndSettle();
    expect(find.textContaining('已连接'), findsOneWidget);
    await tester.tap(find.byType(SwitchListTile));
    await tester.pumpAndSettle();
    expect(enabled, isFalse);
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets('read failures remain visible without claiming connected',
      (tester) async {
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        channel, (_) async => throw PlatformException(code: 'unavailable'));
    await tester.pumpWidget(
        const MaterialApp(home: Scaffold(body: AccessibilityAssistCard())));
    await tester.pumpAndSettle();
    expect(find.textContaining('暂时无法读取'), findsOneWidget);
    expect(find.textContaining('已连接'), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets('late failed status cannot overwrite a successful opt-in',
      (tester) async {
    final pending = Completer<Map<String, dynamic>>();
    var reads = 0;
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(channel,
        (call) async {
      if (call.method == 'status' && ++reads == 2) return pending.future;
      if (call.method == 'setEnabled') {
        return {'enabled': true, 'connected': true, 'captureActive': true};
      }
      return {'enabled': false, 'connected': false, 'captureActive': true};
    });
    await tester.pumpWidget(
        const MaterialApp(home: Scaffold(body: AccessibilityAssistCard())));
    await tester.pumpAndSettle();
    await tester.pump(const Duration(seconds: 2));
    await tester.tap(find.byType(SwitchListTile));
    await tester.pumpAndSettle();
    expect(find.textContaining('已连接'), findsOneWidget);
    pending.completeError(PlatformException(code: 'old_status_failed'));
    await tester.pumpAndSettle();
    expect(find.textContaining('暂时无法读取'), findsNothing);
    expect(tester.widget<SwitchListTile>(find.byType(SwitchListTile)).value,
        isTrue);
    await tester.pumpWidget(const SizedBox());
  });
}
