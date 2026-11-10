import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/capture_sampling.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('pcflash/capture-sampling');
  var enabled = false;
  var fail = false;
  var writes = 0;
  Completer<Map<String, dynamic>>? pending;
  setUp(() {
    enabled = false;
    fail = false;
    writes = 0;
    pending = null;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
      if (call.method == 'setEnabled') {
        writes++;
        if (fail) throw PlatformException(code: 'storage_failed');
        if (pending != null) return pending!.future;
        enabled = (call.arguments as Map)['enabled'] == true;
      }
      return {'enabled': enabled};
    });
  });
  tearDown(() => TestDefaultBinaryMessengerBinding
      .instance.defaultBinaryMessenger
      .setMockMethodCallHandler(channel, null));
  testWidgets(
      'default-off sampling saves only on explicit toggle and can be disabled',
      (t) async {
    await t.pumpWidget(
        const MaterialApp(home: Scaffold(body: CaptureSamplingCard())));
    await t.pumpAndSettle();
    expect(
        t.widget<SwitchListTile>(find.byType(SwitchListTile)).value, isFalse);
    expect(writes, 0);
    await t.tap(find.byType(SwitchListTile));
    await t.pumpAndSettle();
    expect(enabled, isTrue);
    await t.tap(find.byType(SwitchListTile));
    await t.pumpAndSettle();
    expect(enabled, isFalse);
    await t.pumpWidget(const SizedBox());
  });
  testWidgets('failed save preserves prior value and persistent error',
      (t) async {
    await t.pumpWidget(
        const MaterialApp(home: Scaffold(body: CaptureSamplingCard())));
    await t.pumpAndSettle();
    fail = true;
    await t.tap(find.byType(SwitchListTile));
    await t.pumpAndSettle();
    expect(
        t.widget<SwitchListTile>(find.byType(SwitchListTile)).value, isFalse);
    expect(find.textContaining('设置未保存'), findsOneWidget);
    await t.pumpWidget(const SizedBox());
  });
  testWidgets(
      'pending save prevents duplicate writes and waits for actual result',
      (t) async {
    await t.pumpWidget(
        const MaterialApp(home: Scaffold(body: CaptureSamplingCard())));
    await t.pumpAndSettle();
    pending = Completer();
    await t.tap(find.byType(SwitchListTile));
    await t.pump();
    await t.tap(find.byType(SwitchListTile));
    await t.pump();
    expect(writes, 1);
    expect(
        t.widget<SwitchListTile>(find.byType(SwitchListTile)).value, isFalse);
    pending!.complete({'enabled': true});
    await t.pumpAndSettle();
    expect(t.widget<SwitchListTile>(find.byType(SwitchListTile)).value, isTrue);
    await t.pumpWidget(const SizedBox());
  });
}
