import 'dart:convert';

/// Remote task feedback is independent from successful screenshot transport.
class ScreenTaskStatus {
  final CloudTaskProgress? cloudTask;
  final DateTime? observedAt;
  final String capture;
  final String state;
  final String reply;
  final bool pointerReady;
  final bool verified;
  final bool stopConfirmed;
  final List<String> skills;
  const ScreenTaskStatus(
      {required this.capture,
      this.cloudTask,
      this.observedAt,
      this.state = '',
      this.reply = '',
      this.pointerReady = false,
      this.verified = false,
      this.stopConfirmed = false,
      this.skills = const []});

  factory ScreenTaskStatus.parse(String value) {
    if (value.length > 20000) throw const FormatException('共享状态过大');
    final envelope = jsonDecode(value);
    if (envelope is! Map ||
        envelope['capture'] is! String ||
        envelope['task'] is! String) {
      throw const FormatException('共享状态无效');
    }
    final capture = envelope['capture'] as String;
    if (envelope['task'] == '') {
      return ScreenTaskStatus(
          capture: capture,
          cloudTask: CloudTaskProgress.parse(envelope['cloudTask']),
          observedAt: parseStatusTime(envelope['observedAt']));
    }
    final task = jsonDecode(envelope['task'] as String);
    if (task is! Map ||
        task['state'] is! String ||
        task['reply'] is! String ||
        task['pointerReady'] is! bool ||
        task['skills'] is! List ||
        task['barrier'] is! String) {
      throw const FormatException('任务状态无效');
    }
    final skills = <String>[];
    for (final skill in task['skills'] as List) {
      if (skill is! Map ||
          skill['group'] is! String ||
          skill['name'] is! String) {
        throw const FormatException('技能状态无效');
      }
      skills.add('${skill['group']} · ${skill['name']}');
    }
    return ScreenTaskStatus(
        capture: capture,
        cloudTask:
            CloudTaskProgress.parse(task['cloudTask'] ?? envelope['cloudTask']),
        observedAt:
            parseStatusTime(task['observedAt'] ?? envelope['observedAt']),
        state: task['state'],
        reply: task['reply'],
        pointerReady: task['pointerReady'],
        verified: task['verified'] == true,
        stopConfirmed: task['stopConfirmed'] == true,
        skills: List.unmodifiable(skills));
  }

  bool isCloudStale(DateTime now) =>
      observedAt == null ||
      now.difference(observedAt!).inSeconds > 30 ||
      observedAt!.difference(now).inSeconds > 5;

  bool get resultVerified =>
      verified &&
      const {'done', 'succeeded', 'success', 'completed', 'verified'}
          .contains(state);

  String get taskLabel => switch (state) {
        'idle' => '等待新任务',
        'thinking' => '正在理解任务',
        'running' => '任务执行中',
        'verifying' => '正在核验结果',
        'speaking' => '正在播报结果',
        'waiting' => '等待控制板或新画面',
        'done' ||
        'succeeded' ||
        'success' ||
        'completed' ||
        'verified' =>
          resultVerified ? '结果已核验' : '操作已结束，结果待确认',
        'error' || 'failed' => '任务失败',
        'cancelled' => '任务已取消',
        'stopping' => '停止请求已发送，设备停止待确认',
        'stopped' => stopConfirmed ? '任务已停止' : '后续任务已取消，设备停止待确认',
        '' => '等待任务状态',
        _ => '任务状态暂未更新',
      };
}

DateTime? parseStatusTime(dynamic value) =>
    value is String ? DateTime.tryParse(value)?.toUtc() : null;

/// Optional server progress. Missing metadata is unknown, never inferred.
class CloudTaskProgress {
  final String taskId, source, state, stage, description;
  final bool verified, terminal;
  final DateTime? updatedAt;
  const CloudTaskProgress(
      {required this.taskId,
      required this.source,
      required this.state,
      required this.stage,
      required this.description,
      required this.verified,
      required this.terminal,
      this.updatedAt});
  static CloudTaskProgress? parse(dynamic value) {
    if (value is! Map ||
        value['taskId'] is! String ||
        value['state'] is! String ||
        (value['source'] != null && value['source'] is! String)) {
      return null;
    }
    return CloudTaskProgress(
        taskId: value['taskId'],
        source: value['source'] is String ? value['source'] : '',
        state: value['state'],
        stage: value['stage'] is String ? value['stage'] : '',
        description: value['description'] is String ? value['description'] : '',
        verified: value['verified'] == true,
        terminal: value['terminal'] == true,
        updatedAt: parseStatusTime(value['updatedAt']));
  }

  bool get resultVerified =>
      verified &&
      const {'done', 'succeeded', 'success', 'completed', 'verified'}
          .contains(state);
  String get label =>
      ScreenTaskStatus(capture: '', state: state, verified: verified).taskLabel;
  String get sourceLabel => switch (source) {
        'controller' || 'android-app' => '控制手机',
        'telegram' => 'Telegram',
        'openclaw-weixin' => '微信助手',
        'cloud-ai' => '云端 AI',
        'cloud-voice' => '语音助手',
        'ai' => 'AI 助手',
        'local' => '本机任务',
        _ => '来源待更新',
      };
}
