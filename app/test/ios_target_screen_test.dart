import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/services.dart';
import 'package:pcflash/ios_target_screen.dart';
import 'package:pcflash/ble_ota_service.dart';

class QuietBoard extends BleOtaService {
  int scans = 0;
  @override
  Future<void> startScan() async {
    scans++;
  }

  @override
  Future<void> disconnect() async {}
}

void main() {
  testWidgets(
      'iOS target requires explicit USB acknowledgment and never auto scans',
      (tester) async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
            const MethodChannel('pcflash/screen'), (call) async => null);
    tester.view.physicalSize = const Size(800, 2200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final board = QuietBoard();
    await tester.pumpWidget(MaterialApp(home: IosTargetScreen(service: board)));
    expect(find.text('被控 iPhone'), findsOneWidget);
    expect(board.scans, 0);
    expect(find.text('云端进度待更新'), findsOneWidget);
    expect(find.text('本地 OCR · iOS 暂无支持'), findsOneWidget);
    expect(find.textContaining('USB 实际连接未自动核验'), findsOneWidget);
    expect(find.text('结果已核验'), findsNothing);
    final button =
        tester.widget<FilledButton>(find.widgetWithText(FilledButton, '扫描控制板'));
    expect(button.onPressed, isNull);
    expect(find.textContaining('USB 或实际点击已通过'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
    await tester.pump();
    expect(tester.takeException(), isNull);
  });
  testWidgets('iOS failed stop remains unknown rather than confirmed',
      (tester) async {
    tester.view.physicalSize = const Size(800, 2200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('pcflash/screen'),
            (call) async {
      if (call.method == 'stop') throw PlatformException(code: 'unconfirmed');
      return null;
    });
    await tester
        .pumpWidget(MaterialApp(home: IosTargetScreen(service: QuietBoard())));
    await tester.tap(find.text('停止共享与控制'));
    await tester.pumpAndSettle();
    expect(find.textContaining('系统屏幕广播停止未确认'), findsOneWidget);
    expect(find.text('任务已停止'), findsNothing);
    await tester.pumpWidget(const SizedBox());
    await tester.pump();
    expect(tester.takeException(), isNull);
  });
}
