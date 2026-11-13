import 'package:flutter/material.dart';

/// Display only metadata supplied for this same task by the task service.
class ControllerTaskContext extends StatelessWidget {
  const ControllerTaskContext(
      {super.key, required this.task, this.deviceId, required this.connected});
  final Map<String, dynamic> task;
  final String? deviceId;
  final bool connected;

  @override
  Widget build(BuildContext context) {
    final raw = task['cloudTask'];
    final cloud = raw is Map ? raw : const {};
    final metadata = cloud['taskId'] == task['task_id'] ? cloud : const {};
    final source = switch (metadata['source']) {
      'controller' || 'android-app' => '控制手机',
      'telegram' => 'Telegram',
      'openclaw-weixin' => '微信助手',
      'ai' || 'cloud-ai' => '云端 AI 助手',
      'cloud-voice' => '云端语音助手',
      'local' => '本机任务',
      _ => '未提供',
    };
    final stage = metadata['description'];
    final updated = metadata['updatedAt'];
    final target = deviceId == null || deviceId!.isEmpty
        ? '未提供'
        : deviceId!.length > 16
            ? '${deviceId!.substring(0, 16)}…'
            : deviceId!;
    Widget row(String label, String value) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Wrap(spacing: 12, runSpacing: 4, children: [
          Text(label, style: Theme.of(context).textTheme.labelLarge),
          Text(value),
        ]));
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      row('任务来源', source),
      row('目标设备', target),
      row('AI 当前阶段', stage is String && stage.isNotEmpty ? stage : '服务未提供细分阶段'),
      row('同步状态', connected ? '已连接 · 以最近回执为准' : '连接断开 · 以下为上次记录'),
      row(
          '记录时间',
          updated is String && DateTime.tryParse(updated) != null
              ? DateTime.parse(updated).toLocal().toString()
              : '未提供'),
    ]);
  }
}
