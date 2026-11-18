import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/product_widgets.dart';
import 'package:pcflash/theme.dart';
import 'package:pcflash/widgets.dart';

void main() {
  for (final dark in [false, true]) {
    testWidgets('stop action retains contrast in ${dark ? "dark" : "light"}',
        (tester) async {
      await tester.pumpWidget(MaterialApp(
        theme: dark ? AppTheme.build() : AppTheme.light(),
        home: Scaffold(
          bottomNavigationBar: Builder(
            builder: (context) => ProductActionBar(
              child: FilledButton(
                style: productStopButtonStyle(context),
                onPressed: () {},
                child: const Text('停止手机操作'),
              ),
            ),
          ),
        ),
      ));
      final button = tester.widget<FilledButton>(find.byType(FilledButton));
      final foreground = button.style!.foregroundColor!.resolve({})!;
      final background = button.style!.backgroundColor!.resolve({})!;
      expect(_contrast(foreground, background), greaterThanOrEqualTo(4.5));
    });

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
      final contrast =
          _contrast(fg, Color.alphaBlend(fg.withValues(alpha: .1), bg));
      expect(contrast, greaterThanOrEqualTo(4.5));
    });
  }
}

double _contrast(Color foreground, Color background) {
  final ink = foreground.computeLuminance() + .05;
  final surface = background.computeLuminance() + .05;
  return ink > surface ? ink / surface : surface / ink;
}
