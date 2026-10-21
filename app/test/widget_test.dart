import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/main.dart';

void main() {
  testWidgets('app boots', (tester) async {
    await tester.pumpWidget(const PcFlashApp());
    expect(find.text('PhoneCtl Flash'), findsOneWidget);
  });
}
