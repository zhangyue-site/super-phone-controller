import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/main.dart';
import 'package:pcflash/usb_launch.dart';

const app = MethodChannel('pcflash/app');
void main() {
  setUp(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(UsbLaunch.channel, (_) async => null);
  });
  tearDown(() {
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(UsbLaunch.channel, null);
    messenger.setMockMethodCallHandler(app, null);
  });
  for (final name in ['system', 'light', 'dark']) {
    testWidgets('restores saved appearance $name', (tester) async {
      tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
          app, (call) async => call.method == 'appearance' ? name : null);
      await tester.pumpWidget(const PcFlashApp());
      await tester.pumpAndSettle();
      expect(tester.widget<MaterialApp>(find.byType(MaterialApp)).themeMode,
          ThemeMode.values.firstWhere((value) => value.name == name));
      await tester.pumpWidget(const SizedBox());
    });
  }
  testWidgets('unavailable preference defaults to system', (tester) async {
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        app, (_) async => throw MissingPluginException());
    await tester.pumpWidget(const PcFlashApp());
    await tester.pumpAndSettle();
    expect(tester.widget<MaterialApp>(find.byType(MaterialApp)).themeMode,
        ThemeMode.system);
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets(
      'late saved appearance cannot override user choice and choice is persisted',
      (tester) async {
    final pending = Completer<String>();
    final saved = <Map<Object?, Object?>>[];
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(app,
        (call) async {
      if (call.method == 'appearance') return pending.future;
      if (call.method == 'setAppearance') {
        saved.add(call.arguments as Map<Object?, Object?>);
      }
      return null;
    });
    await tester.pumpWidget(const PcFlashApp());
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('显示主题'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('深色'));
    await tester.pumpAndSettle();
    expect(saved, [
      {'mode': 'dark'}
    ]);
    pending.complete('light');
    await tester.pumpAndSettle();
    expect(tester.widget<MaterialApp>(find.byType(MaterialApp)).themeMode,
        ThemeMode.dark);
    await tester.pumpWidget(const SizedBox());
  });
}
