import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/app_release.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  testWidgets('uses installed metadata and opens official update entry',
      (tester) async {
    final calls = <String>[];
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(AppRelease.channel, (call) async {
      calls.add(call.method);
      return call.method == 'info'
          ? {'versionName': '9.8.7', 'versionCode': 123}
          : null;
    });
    addTearDown(() => TestDefaultBinaryMessengerBinding
        .instance.defaultBinaryMessenger
        .setMockMethodCallHandler(AppRelease.channel, null));
    await tester.pumpWidget(MaterialApp(
        home: Builder(
            builder: (context) => TextButton(
                onPressed: () => AppRelease.show(context),
                child: const Text('版本')))));
    await tester.tap(find.text('版本'));
    await tester.pumpAndSettle();
    expect(find.textContaining('9.8.7（123）'), findsOneWidget);
    await tester.tap(find.text('官方下载与更新'));
    await tester.pump();
    expect(calls, ['info', 'openDownload']);
  });
  testWidgets('metadata failure does not claim release version is installed',
      (tester) async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(AppRelease.channel,
            (_) async => throw PlatformException(code: 'unavailable'));
    addTearDown(() => TestDefaultBinaryMessengerBinding
        .instance.defaultBinaryMessenger
        .setMockMethodCallHandler(AppRelease.channel, null));
    await tester.pumpWidget(MaterialApp(
        home: Builder(
            builder: (context) => TextButton(
                onPressed: () => AppRelease.show(context),
                child: const Text('版本')))));
    await tester.tap(find.text('版本'));
    await tester.pumpAndSettle();
    expect(find.textContaining('暂时无法读取'), findsOneWidget);
    expect(find.textContaining('1.0.7'), findsNothing);
  });
  testWidgets('missing update URL gives no placeholder or personal fallback',
      (tester) async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(AppRelease.channel, (call) async {
      if (call.method == 'info') return {'versionName': '1', 'versionCode': 1};
      throw PlatformException(code: 'not_configured');
    });
    addTearDown(() => TestDefaultBinaryMessengerBinding
        .instance.defaultBinaryMessenger
        .setMockMethodCallHandler(AppRelease.channel, null));
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: Builder(
                builder: (context) => TextButton(
                    onPressed: () => AppRelease.show(context),
                    child: const Text('版本'))))));
    await tester.tap(find.text('版本'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('官方下载与更新'));
    await tester.pumpAndSettle();
    expect(find.text('更新入口未配置或暂时无法打开，请联系应用维护者'), findsOneWidget);
    expect(find.byType(SnackBar), findsNothing);
    expect(find.text('关闭').hitTestable(), findsOneWidget);
    expect(find.textContaining('example.invalid'), findsNothing);
  });

  testWidgets('small large-text update dialog can close during a launch',
      (tester) async {
    tester.view.physicalSize = const Size(320, 568);
    tester.view.devicePixelRatio = 1;
    tester.platformDispatcher.textScaleFactorTestValue = 1.8;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    final open = Completer<void>();
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(AppRelease.channel, (call) async {
      if (call.method == 'info') return {'versionName': '1', 'versionCode': 1};
      await open.future;
      return null;
    });
    addTearDown(
        () => messenger.setMockMethodCallHandler(AppRelease.channel, null));
    await tester.pumpWidget(MaterialApp(
        home: Builder(
            builder: (context) => TextButton(
                onPressed: () => AppRelease.show(context),
                child: const Text('版本')))));
    await tester.tap(find.text('版本'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('官方下载与更新'));
    await tester.pump();
    expect(tester.widget<FilledButton>(find.byType(FilledButton)).onPressed,
        isNull);
    await tester.tap(find.text('关闭'));
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsNothing);
    open.complete();
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });
}
