import 'package:flutter/material.dart';
import 'screen_task_status.dart';

class TargetProgressCard extends StatelessWidget {
  final ScreenTaskStatus status;
  final bool connected;
  final DateTime now;
  const TargetProgressCard(
      {super.key,
      required this.status,
      required this.connected,
      required this.now});
  @override
  Widget build(BuildContext context) {
    final task = status.cloudTask;
    final stale = !connected || status.isCloudStale(now);
    final updated = status.observedAt;
    final age = updated == null ? null : now.difference(updated).inSeconds;
    return Card(
        child: Padding(
            padding: const EdgeInsets.all(20),
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                Icon(stale
                    ? Icons.cloud_off_outlined
                    : Icons.cloud_done_outlined),
                const SizedBox(width: 12),
                Expanded(
                    child: Text(stale ? '云端进度待更新' : '云端同步正常',
                        style: Theme.of(context).textTheme.titleMedium))
              ]),
              const SizedBox(height: 8),
              Text(age == null ? '同步观察时间未知' : '同步观察：${age < 0 ? 0 : age} 秒前'),
              Text(task?.updatedAt == null
                  ? '任务更新时间未知'
                  : '任务更新：${task!.updatedAt!.toLocal().toIso8601String().replaceFirst('T', ' ')}'),
              if (stale)
                const Padding(
                    padding: EdgeInsets.only(top: 8),
                    child: Text('当前不是实时进度。已发动作结果仍需确认；恢复后不会重放旧操作。')),
              const Divider(height: 28),
              Text(task == null ? '等待任务状态' : task.label,
                  style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 8),
              Text('来源：${task?.sourceLabel ?? '待更新'} · 目标：这台手机'),
              if (task?.description.isNotEmpty == true)
                Padding(
                    padding: const EdgeInsets.only(top: 12),
                    child: Text(task!.description)),
              if (task?.stage.isNotEmpty == true)
                Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Text('当前阶段：${task!.label}')),
              if (task == null && status.state.isNotEmpty)
                Padding(
                    padding: const EdgeInsets.only(top: 12),
                    child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text('最近任务反馈'),
                          const SizedBox(height: 4),
                          Text(status.taskLabel),
                        ])),
              const SizedBox(height: 12),
              const Text('控制板回执不代表任务成功；操作结果需要新画面核验。'),
            ])));
  }
}

/// Persistent pairing displays digits without manufacturing an expiry timer.
class TargetBindingCode extends StatelessWidget {
  final String code;
  final bool persistent;
  const TargetBindingCode(
      {super.key, required this.code, required this.persistent});
  @override
  Widget build(BuildContext context) =>
      Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(persistent
            ? '我的绑定码 · 持续有效，重开 App 不变。请只交给自己的控制手机。'
            : '兼容连接码 · 两分钟内有效，仅可使用一次。'),
        const SizedBox(height: 12),
        SelectableText(code,
            style: persistent
                ? Theme.of(context)
                    .textTheme
                    .displayMedium
                    ?.copyWith(letterSpacing: 12)
                : null),
      ]);
}
