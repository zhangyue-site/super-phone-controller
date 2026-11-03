import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:pcflash/main.dart' as app;
import 'package:pcflash/role_home.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  testWidgets('cold launch reaches role home with native scene bridges',
      (tester) async {
    app.main();
    await tester.pumpAndSettle();
    expect(find.byType(RoleHome), findsOneWidget);
    final info = await const MethodChannel('pcflash/app')
        .invokeMapMethod<String, dynamic>('info')
        .timeout(const Duration(seconds: 10));
    expect(info?['versionName'], isNotEmpty);
    expect(info?['versionCode'], isA<int>());
    final usb = await const MethodChannel('pcflash/usb')
        .invokeMethod<dynamic>('snapshot')
        .timeout(const Duration(seconds: 10));
    expect(usb, isNull);
    final state = await const MethodChannel('pcflash/screen')
        .invokeMethod<String>('status')
        .timeout(const Duration(seconds: 10));
    expect(state, contains('"active":false'));
  });
}
