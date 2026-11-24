import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/role_home.dart';

void main() {
  const channel = MethodChannel('pcflash/app');
  testWidgets(
      'wireless debugging opens Settings only on tap and refreshes on return',
      (tester) async {
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    final methods = <String>[];
    int? port;
    bool? enabled;
    messenger.setMockMethodCallHandler(channel, (call) async {
      methods.add(call.method);
      if (call.method == 'wirelessDebugStatus') {
        return {'port': port, 'enabled': enabled};
      }
      if (call.method == 'openDeveloperSettings') return null;
      throw UnsupportedError(call.method);
    });
    addTearDown(() => messenger.setMockMethodCallHandler(channel, null));
    await tester.pumpWidget(
        const MaterialApp(home: Scaffold(body: WirelessDebugCard())));
    await tester.pumpAndSettle();
    expect(methods, ['wirelessDebugStatus']);
    expect(find.text('请在系统设置中确认'), findsOneWidget);
    await tester.tap(find.text('打开开发者选项'));
    await tester.pumpAndSettle();
    expect(methods, ['wirelessDebugStatus', 'openDeveloperSettings']);
    port = 40123;
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pumpAndSettle();
    expect(find.text('系统报告的无线调试连接端口：40123'), findsOneWidget);
    port = -1;
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pumpAndSettle();
    expect(find.text('请在系统设置中确认'), findsOneWidget);
    for (final value in [true, false]) {
      enabled = value;
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pumpAndSettle();
      expect(
          find.text(value ? '系统已开启，连接端口请在系统页查看' : '无线调试已关闭'), findsOneWidget);
    }
    expect(methods.where((m) => m == 'openDeveloperSettings'), hasLength(1));
  });

  testWidgets('system settings stay closed when screen sharing is active',
      (tester) async {
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(channel, (call) async {
      if (call.method == 'openDeveloperSettings') {
        throw PlatformException(code: 'sharing_active');
      }
      return null;
    });
    addTearDown(() => messenger.setMockMethodCallHandler(channel, null));
    await tester.pumpWidget(
        const MaterialApp(home: Scaffold(body: WirelessDebugCard())));
    await tester.pumpAndSettle();
    await tester.tap(find.text('打开开发者选项'));
    await tester.pump();
    expect(find.text('请先结束屏幕共享，再打开开发者选项'), findsOneWidget);
  });

  for (final brightness in Brightness.values) {
    testWidgets('role selection explains sharing only on target in $brightness',
        (tester) async {
      tester.view.physicalSize = const Size(320, 568);
      tester.view.devicePixelRatio = 1;
      tester.platformDispatcher.textScaleFactorTestValue = 1.6;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      var selected = '';
      await tester.pumpWidget(MaterialApp(
          theme: ThemeData(brightness: brightness),
          home: RoleHome(
              onController: () => selected = 'controller',
              onTarget: () => selected = 'target')));
      expect(find.text('控制手机'), findsOneWidget);
      expect(find.text('被控手机'), findsOneWidget);
      expect(find.text('发送任务、查看进度，无需共享本机屏幕'), findsOneWidget);
      expect(find.text('连接控制板，并按系统提示共享屏幕'), findsOneWidget);
      await tester.ensureVisible(find.text('控制手机'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('控制手机'));
      expect(selected, 'controller');
      await tester.ensureVisible(find.text('被控手机'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('被控手机'));
      expect(selected, 'target');
      expect(tester.takeException(), isNull);
    });
  }
}
