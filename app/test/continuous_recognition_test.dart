import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/local_auto_loop.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('pcflash/local-loop');
  var active = false;
  var count = 0;
  var received = 0;
  var starts = 0;
  var stops = 0;
  var fail = false;
  setUp(() {
    active = false;
    count = 0;
    received = 0;
    starts = 0;
    stops = 0;
    fail = false;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
      switch (call.method) {
        case 'billOcrStatus':
          return active ? '已识别 $count / 10 帧' : '连续文字识别未开始';
        case 'recognitionStatus':
          return {
            'source': 'ocr',
            'active': active,
            'count': count,
            'received': received
          };
        case 'startBillOcr':
          starts++;
          if (fail) throw PlatformException(code: 'unavailable');
          active = true;
          return true;
        case 'stopBillOcr':
          active = false;
          stops++;
          return null;
        default:
          return null;
      }
    });
  });
  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, null);
  });
  Future<void> show(WidgetTester tester) async {
    await tester.pumpWidget(const MaterialApp(
        home:
            Scaffold(body: SingleChildScrollView(child: LocalAutoLoopCard()))));
    await tester.pump();
  }

  testWidgets(
      'OCR start is single-flight and local progress differs from receipt',
      (tester) async {
    await show(tester);
    await tester.tap(find.text('开始连续文字识别'));
    await tester.pump();
    await tester.pump();
    expect(starts, 1);
    final start = tester
        .widget<FilledButton>(find.widgetWithText(FilledButton, '开始连续文字识别'));
    expect(start.onPressed, isNull);
    final buttons = tester
        .widget<FilledButton>(find.widgetWithText(FilledButton, '开始一轮识别'));
    expect(buttons.onPressed, isNull);
    count = 10;
    received = 6;
    await tester.pump(const Duration(seconds: 1));
    await tester.pump();
    expect(find.text('本轮已识别 10 / 10 帧 · 106 已接收 6 / 10 帧'), findsOneWidget);
    await tester.tap(find.text('停止文字识别'));
    await tester.pump();
    await tester.pump();
    expect(stops, 1);
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets('start failure remains visible and controls recover',
      (tester) async {
    await show(tester);
    fail = true;
    await tester.tap(find.text('开始连续文字识别'));
    await tester.pump();
    await tester.pump();
    expect(find.text('无法读取识别状态，请检查屏幕共享'), findsOneWidget);
    final start = tester
        .widget<FilledButton>(find.widgetWithText(FilledButton, '开始连续文字识别'));
    expect(start.onPressed, isNotNull);
    await tester.pumpWidget(const SizedBox());
  });
}
