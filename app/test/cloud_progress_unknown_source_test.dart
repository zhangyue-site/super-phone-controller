import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/screen_task_status.dart';

void main() {
  test('server cancellation alone never proves a device stop', () {
    const status = ScreenTaskStatus(capture: '', state: 'stopped');
    expect(status.taskLabel, '后续任务已取消，设备停止待确认');
    const confirmed =
        ScreenTaskStatus(capture: '', state: 'stopped', stopConfirmed: true);
    expect(confirmed.taskLabel, '任务已停止');
  });
  test('unknown source retains real cloud task and stage', () {
    final task = CloudTaskProgress.parse({
      'taskId': 'task-1',
      'state': 'running',
      'source': null,
      'stage': 'execution',
      'description': '正在执行并核验'
    });
    expect(task, isNotNull);
    expect(task!.sourceLabel, '来源待更新');
    expect(task.description, '正在执行并核验');
  });
}
