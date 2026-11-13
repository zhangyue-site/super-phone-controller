import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/screen_task_status.dart';
import 'package:pcflash/target_progress_card.dart';

void main() {
  testWidgets('persistent leading-zero code has no expiry countdown',
      (tester) async {
    await tester.pumpWidget(const MaterialApp(
        home:
            Scaffold(body: TargetBindingCode(code: '0123', persistent: true))));
    expect(find.text('0123'), findsOneWidget);
    expect(find.textContaining('持续有效'), findsOneWidget);
    expect(find.textContaining('两分钟'), findsNothing);
    await tester.pump(const Duration(minutes: 3));
    expect(find.text('0123'), findsOneWidget);
  });
  testWidgets('offline retains progress with explicit uncertainty',
      (tester) async {
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: TargetProgressCard(
                status: ScreenTaskStatus(
                    capture: '共享中',
                    observedAt: DateTime.utc(2026),
                    cloudTask: const CloudTaskProgress(
                        taskId: 't',
                        source: 'android-app',
                        state: 'done',
                        stage: 'ack',
                        description: '等待画面',
                        verified: false,
                        terminal: true)),
                connected: false,
                now: DateTime.utc(2026)))));
    expect(find.text('云端进度待更新'), findsOneWidget);
    expect(find.text('操作已结束，结果待确认'), findsOneWidget);
    expect(find.text('结果已核验'), findsNothing);
    expect(find.textContaining('已发动作结果仍需确认'), findsOneWidget);
  });
}
