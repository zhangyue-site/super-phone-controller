/// 浮窗抢屏协议状态（云中继 poll 回执刷新，浮窗渲染读取）
class HumanPillState {
  static int pauseLeft = 0;
  static int askLeft = 0;
  static String taskText = '';
  static void updateFromReceipt(Map<String, dynamic>? r) {
    if (r == null) return;
    int asInt(dynamic v) => v is int ? v : (v is num ? v.toInt() : 0);
    pauseLeft = asInt(r['humanPauseLeft']);
    askLeft = asInt(r['humanAskLeft']);
    taskText = (r['task_head'] ?? '') as String;
  }

  static bool get active => pauseLeft > 0 || askLeft > 0;
}

/// 原生浮窗点击 -> Dart -> 云中继 human-tap 上报的桥
class HumanTapBridge {
  static Future<void> Function()? onHumanTap;
  static Future<void> fire() async {
    try {
      await onHumanTap?.call();
    } catch (_) {}
  }
}
