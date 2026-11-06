import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/screen_task_status.dart';
import 'package:pcflash/screen_share.dart';
import 'package:pcflash/usb_launch.dart';
import 'package:pcflash/usb_target_screen.dart';

Map<String, dynamic> task(String state,
        {Object? verified, bool include = true}) =>
    {
      'state': state,
      'reply': '已通过画面核验完成：打开设置。',
      'pointerReady': false,
      'skills': [],
      'barrier': '',
      if (include) 'verified': verified,
    };
String envelope(Map<String, dynamic> value) => jsonEncode({
      'active': true,
      'capture': '共享中',
      'task': jsonEncode(value),
    });

void main() {
  test('verification requires explicit boolean and successful terminal state',
      () {
    for (final state in ['done', 'completed', 'verified']) {
      for (final flag in [null, false, 'true', 1]) {
        final parsed = ScreenTaskStatus.parse(
            envelope(task(state, verified: flag, include: flag != null)));
        expect(parsed.resultVerified, isFalse);
        expect(parsed.taskLabel, '操作已结束，结果待确认');
      }
    }
    for (final state in [
      'running',
      'thinking',
      'verifying',
      'speaking',
      'failed',
      'error',
      'cancelled',
      'stopped',
      'idle'
    ]) {
      final parsed =
          ScreenTaskStatus.parse(envelope(task(state, verified: true)));
      expect(parsed.resultVerified, isFalse, reason: state);
      expect(parsed.taskLabel, isNot('结果已核验'), reason: state);
    }
    final parsed =
        ScreenTaskStatus.parse(envelope(task('done', verified: true)));
    expect(parsed.resultVerified, isTrue);
    expect(parsed.taskLabel, '结果已核验');
  });

  testWidgets(
      'B consumes native status updates without trusting reply or stale verification',
      (tester) async {
    var current = task('running', verified: true);
    var consentRequests = 0;
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(UsbLaunch.channel, (call) async {
      if (call.method == 'info') {
        return {'protocol': 1, 'device': 'test-board', 'usbSerial': 'RESULT27'};
      }
      return null;
    });
    messenger.setMockMethodCallHandler(ScreenShare.channel, (call) async {
      if (call.method == 'start') consentRequests++;
      if (call.method == 'status') return envelope(current);
      if (call.method == 'usbWindow') return {'state': 'idle'};
      return null;
    });
    addTearDown(() {
      messenger.setMockMethodCallHandler(UsbLaunch.channel, null);
      messenger.setMockMethodCallHandler(ScreenShare.channel, null);
    });
    await tester.pumpWidget(MaterialApp(
        home: UsbTargetScreen(
      attachment:
          const UsbAttachment('RESULT27', 'result-27-session', null, null),
      isCurrent: () => true,
      renewCapture: (_) async {},
    )));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('最近任务反馈'), 150);
    await tester.pumpAndSettle();
    Future<void> update(Map<String, dynamic> next, String label) async {
      current = next;
      await tester.pump(const Duration(seconds: 2));
      await tester.pumpAndSettle();
      expect(find.text(label), findsOneWidget);
      if (label != '结果已核验') expect(find.text('结果已核验'), findsNothing);
    }

    await update(task('running', verified: true), '任务执行中');
    await update(task('done', include: false), '操作已结束，结果待确认');
    await update(task('done', verified: false), '操作已结束，结果待确认');
    await update(task('done', verified: 'true'), '操作已结束，结果待确认');
    await update(task('done', verified: true), '结果已核验');
    await update(task('failed', verified: true), '任务失败');
    await update(task('cancelled', verified: true), '任务已取消');
    await update(task('running', include: false), '任务执行中');
    expect(consentRequests, 0);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
  });
}
