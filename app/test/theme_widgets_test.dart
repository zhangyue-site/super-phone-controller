import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/theme.dart';
import 'package:pcflash/widgets.dart';

void main() {
  for (final dark in [false, true]) {
    testWidgets(
        'shared firmware widgets remain legible at 320px, scale 1.6 (${dark ? "dark" : "light"})',
        (tester) async {
      tester.view.physicalSize = const Size(320, 568);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      await tester.pumpWidget(MaterialApp(
          theme: dark ? AppTheme.build() : AppTheme.light(),
          home: Builder(
              builder: (context) => MediaQuery(
                    data: MediaQuery.of(context)
                        .copyWith(textScaler: const TextScaler.linear(1.6)),
                    child: const Scaffold(
                        body: SingleChildScrollView(
                            child: Column(children: [
                      InfoBanner(
                          icon: Icons.warning_amber, text: '固件校验失败，请检查连接后重试。'),
                      StepList(
                          steps: [('连接设备', 2), ('传输固件', 1), ('等待重启确认', 0)]),
                      RingProgress(value: .5, center: '50%', subtitle: '正在传输'),
                    ]))),
                  ))));
      await tester.pump(const Duration(milliseconds: 250));
      expect(tester.takeException(), isNull);
      final banner = tester.widget<Text>(find.text('固件校验失败，请检查连接后重试。'));
      final bg =
          (dark ? AppTheme.build() : AppTheme.light()).colorScheme.surface;
      final fg = banner.style!.color!;
      final a = fg.computeLuminance();
      final b =
          Color.alphaBlend(fg.withValues(alpha: .1), bg).computeLuminance();
      final contrast =
          (a > b ? a + .05 : b + .05) / (a > b ? b + .05 : a + .05);
      expect(contrast, greaterThanOrEqualTo(4.5));
    });
  }
}
