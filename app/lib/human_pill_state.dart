// 浮窗抢屏协议状态（云中继 poll 回执刷新，浮窗渲染读取）
// v1.4.23: + 任务历史本地记录（task_head 变化驱动，JSON 持久化，上限 30 条）
import 'dart:convert';
import 'dart:io';
import 'package:path_provider/path_provider.dart';

class HumanPillState {
  static int pauseLeft = 0;
  static int askLeft = 0;
  static String taskText = '';
  static String lastReply = '';

  /// 任务历史（最新在前）：{ts, head, state: 运行中|已结束, reply}
  static final List<Map<String, dynamic>> history = <Map<String, dynamic>>[];
  static bool _loaded = false;
  static String? _openHead;

  static void updateFromReceipt(Map<String, dynamic>? r) {
    if (r == null) return;
    int asInt(dynamic v) => v is int ? v : (v is num ? v.toInt() : 0);
    pauseLeft = asInt(r['humanPauseLeft']);
    askLeft = asInt(r['humanAskLeft']);
    lastReply = (r['reply'] ?? '') as String;
    final head = ((r['task_head'] ?? '') as String).trim();
    final prev = taskText;
    taskText = head;
    if (head == prev && head.isNotEmpty) {
      _touchOpen(head, lastReply);
      return;
    }
    _trackHistory(head, lastReply);
  }

  static void _trackHistory(String head, String reply) async {
    if (!_loaded) {
      _loaded = true;
      await _load();
    }
    if (head.isNotEmpty) {
      if (head != _openHead) {
        _closeOpen(reply);
        _openHead = head;
        history.insert(0, {
          'ts': DateTime.now().millisecondsSinceEpoch,
          'head': head,
          'state': '运行中',
          'reply': reply,
        });
        _trim();
        await _save();
      } else {
        _touchOpen(head, reply);
      }
    } else if (_openHead != null) {
      _closeOpen(reply);
      await _save();
    }
  }

  static void _touchOpen(String head, String reply) {
    if (history.isEmpty) return;
    final rec = history.first;
    if (rec['head'] == head && reply.isNotEmpty && rec['reply'] != reply) {
      rec['reply'] = reply;
      _save();
    }
  }

  static void _closeOpen(String reply) {
    if (_openHead == null) return;
    for (final rec in history) {
      if (rec['head'] == _openHead && rec['state'] == '运行中') {
        rec['state'] = '已结束';
        if ((rec['reply'] as String? ?? '').isEmpty) rec['reply'] = reply;
        break;
      }
    }
    _openHead = null;
  }

  static void _trim() {
    while (history.length > 30) {
      history.removeLast();
    }
  }

  static Future<File> _file() async {
    final dir = await getApplicationDocumentsDirectory();
    return File('${dir.path}/task_history.json');
  }

  static Future<void> _load() async {
    try {
      final f = await _file();
      if (await f.exists()) {
        final list = jsonDecode(await f.readAsString()) as List;
        history
          ..clear()
          ..addAll(list
              .map((e) => Map<String, dynamic>.from(e as Map))
              .toList());
      }
    } catch (_) {}
  }

  static Future<void> _save() async {
    try {
      final f = await _file();
      await f.writeAsString(jsonEncode(history));
    } catch (_) {}
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
