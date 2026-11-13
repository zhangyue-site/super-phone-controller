import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/controller_task_context.dart';

void main() {
  testWidgets('missing and mismatched metadata remains unknown',
      (tester) async {
    await tester.pumpWidget(const MaterialApp(
        home: Scaffold(
            body: ControllerTaskContext(task: {
      'task_id': 'current',
      'cloudTask': {
        'taskId': 'other',
        'source': 'telegram',
        'description': '不应显示'
      }
    }, connected: false))));
    expect(find.text('不应显示'), findsNothing);
    expect(find.text('Telegram'), findsNothing);
    expect(find.text('未提供'), findsNWidgets(3));
    expect(find.text('连接断开 · 以下为上次记录'), findsOneWidget);
  });
  testWidgets(
      'same task uses public stage and friendly source without fake success',
      (tester) async {
    await tester.pumpWidget(const MaterialApp(
        home: Scaffold(
            body: ControllerTaskContext(task: {
      'task_id': 'current',
      'cloudTask': {
        'taskId': 'current',
        'source': 'openclaw-weixin',
        'stage': 'running',
        'description': '正在获取新画面',
        'updatedAt': '2026-11-13T01:00:00Z'
      }
    }, deviceId: 'board', connected: true))));
    expect(find.text('微信助手'), findsOneWidget);
    expect(find.text('正在获取新画面'), findsOneWidget);
    expect(find.text('running'), findsNothing);
    expect(find.textContaining('已完成'), findsNothing);
  });
}
