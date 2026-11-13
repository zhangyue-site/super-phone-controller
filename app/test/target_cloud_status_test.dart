import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/screen_task_status.dart';

void main() {
  String payload(Map<String, dynamic> extra) => jsonEncode({
        'capture': '共享中',
        'task': jsonEncode({
          'state': 'running',
          'reply': '',
          'pointerReady': false,
          'skills': [],
          'barrier': '',
          ...extra
        })
      });
  test('legacy fields remain unknown rather than live', () {
    final status = ScreenTaskStatus.parse(payload({}));
    expect(status.cloudTask, isNull);
    expect(status.isCloudStale(DateTime.utc(2026)), isTrue);
  });
  test('cloud progress uses server timestamp, no ACK success', () {
    final status = ScreenTaskStatus.parse(payload({
      'observedAt': '2026-11-13T02:00:00Z',
      'cloudTask': {
        'taskId': 'a',
        'source': 'android-app',
        'state': 'done',
        'stage': 'ack',
        'description': '已回执',
        'verified': false,
        'terminal': true,
        'updatedAt': '2026-11-13T01:59:59Z'
      }
    }));
    expect(status.cloudTask!.resultVerified, isFalse);
    expect(status.isCloudStale(DateTime.utc(2026, 11, 13, 2, 0, 10)), isFalse);
    expect(status.isCloudStale(DateTime.utc(2026, 11, 13, 2, 1)), isTrue);
  });
  test('malformed optional cloud fields remain unknown', () {
    final status = ScreenTaskStatus.parse(payload({
      'observedAt': 123,
      'cloudTask': {'state': 'done', 'verified': true}
    }));
    expect(status.cloudTask, isNull);
    expect(status.observedAt, isNull);
  });
  test('cloud success requires explicit successful terminal evidence', () {
    CloudTaskProgress parse(Map<String, dynamic> extra) =>
        CloudTaskProgress.parse(
            {'taskId': 't', 'state': 'done', 'verified': true, ...extra})!;
    expect(parse({}).resultVerified, isFalse);
    expect(parse({}).label, '操作已结束，结果待确认');
    expect(parse({'terminal': false}).resultVerified, isFalse);
    expect(
        parse({'state': 'running', 'terminal': true}).resultVerified, isFalse);
    expect(parse({'state': 'running', 'terminal': true}).label, '任务执行中');
    expect(parse({'terminal': true}).resultVerified, isTrue);
    expect(parse({'terminal': true}).label, '结果已核验');
  });
  test('only returned public phases receive localized labels', () {
    for (final entry in {
      'execution': '正在操作手机',
      'verification': '正在核验新画面',
      'confirmation': '等待任务确认',
      'queue': '等待执行',
      'stopping': '正在请求停止',
      'unexpected_internal_value': '阶段待更新'
    }.entries) {
      final task = CloudTaskProgress.parse(
          {'taskId': 't', 'state': 'running', 'stage': entry.key})!;
      expect(task.phaseLabel, entry.value);
    }
  });
}
