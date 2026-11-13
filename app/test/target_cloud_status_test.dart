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
}
