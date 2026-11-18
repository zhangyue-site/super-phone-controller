import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/role_home.dart';
import 'package:pcflash/theme.dart';

void main() {
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
          theme: brightness == Brightness.dark
              ? AppTheme.build()
              : AppTheme.light(),
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

  testWidgets('wide home presents both choices side by side', (tester) async {
    tester.view.physicalSize = const Size(900, 640);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(MaterialApp(
        theme: AppTheme.light(),
        home: RoleHome(onController: () {}, onTarget: () {})));

    final controller = tester.getTopLeft(find.text('控制手机'));
    final target = tester.getTopLeft(find.text('被控手机'));
    expect(controller.dy, target.dy);
    expect(controller.dx, lessThan(target.dx));
    expect(tester.takeException(), isNull);
  });

  testWidgets('existing screen share remains a visible shortcut to target',
      (tester) async {
    var targetOpened = false;
    await tester.pumpWidget(MaterialApp(
        theme: AppTheme.build(),
        home: RoleHome(
            sharingActive: true,
            onController: () {},
            onTarget: () => targetOpened = true)));

    final sharing = find.text('屏幕共享仍在继续');
    await tester.ensureVisible(sharing);
    await tester.tap(sharing);
    expect(targetOpened, isTrue);
    expect(tester.takeException(), isNull);
  });
}
