import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/role_home.dart';

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
