import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/services.dart';
import 'package:pcflash/ios_target_screen.dart';
import 'package:pcflash/ble_ota_service.dart';
class QuietBoard extends BleOtaService {
  int scans = 0;
  @override
  Future<void> startScan() async { scans++; }
  @override
  Future<void> disconnect() async {}
}
void main() {
 testWidgets('iOS target requires explicit USB acknowledgment and never auto scans', (tester) async {
  TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
    const MethodChannel('pcflash/screen'), (call) async => null);
  final board=QuietBoard();
  await tester.pumpWidget(MaterialApp(home:IosTargetScreen(service:board)));
  expect(find.text('被控 iPhone'),findsOneWidget);
  expect(board.scans,0);
  final button=tester.widget<FilledButton>(find.widgetWithText(FilledButton,'扫描控制板'));
  expect(button.onPressed,isNull);
  expect(find.textContaining('USB 或实际点击已通过'),findsOneWidget);
  await tester.pumpWidget(const SizedBox());
  await tester.pump();
  expect(tester.takeException(),isNull);
 });
}
