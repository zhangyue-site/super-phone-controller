import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart'
    show defaultTargetPlatform, TargetPlatform;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'diagnostics.dart';
import 'screen_share.dart';
import 'overlay_status.dart';
import 'target_session.dart';

/// 状态灯编码，与 android .../OverlayPill.kt 的常量一一对应。
const int pillGreen = 0, pillYellow = 1, pillRed = 2, pillGray = 3;

/// 悬浮状态条（pill）控制器。
///
/// 数据全部来自 App 内已有状态源：共享状态读原生 `pcflash/screen` 的
/// volatile 字段（无网络请求）、控制连接读 `TargetSession.retainedClient`
/// 的 `authorized`、任务回执时间读 `ControlClient.lastReceiptAt`
/// （来自 CloudRelay 心跳/回执时间戳）、电量走原生电池广播。
/// 渲染交给原生 WindowManager（TYPE_APPLICATION_OVERLAY），见 OverlayPill.kt。
class OverlayPill with WidgetsBindingObserver {
  OverlayPill._();
  static final OverlayPill instance = OverlayPill._();
  static const _channel = MethodChannel('pcflash/pill');

  /// 每次启动（进程）内有效：用户关闭 pill 后本次不再出现。
  bool _closed = false;
  bool _started = false;
  bool _shown = false;
  bool _syncing = false;
  bool _permissionMissingReported = false;
  AppLifecycleState? _state;
  Timer? _poll;
  String? _lastPayloadKey;

  /// main.dart 启动时调用一次；注册生命周期观察与原生回调。
  void start() {
    if (_started) return;
    _started = true;
    WidgetsBinding.instance.addObserver(this);
    _channel.setMethodCallHandler((call) async {
      if (call.method == 'onClosed') _onClosed();
      return null;
    });
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _state = state;
    if (state == AppLifecycleState.resumed ||
        state == AppLifecycleState.paused ||
        state == AppLifecycleState.hidden) {
      unawaited(_sync());
    }
    // inactive（通知栏下拉、分屏失焦等）不改变现状，避免闪烁。
  }

  void _onClosed() {
    _closed = true;
    _shown = false;
    _lastPayloadKey = null;
    _stopPoll();
    SafeDiagnostics.record('pill_overlay',
        phase: 'overlay', reason: 'user_closed');
  }

  void _stopPoll() {
    _poll?.cancel();
    _poll = null;
  }

  Future<void> _sync() async {
    if (!Platform.isAndroid || _syncing) return;
    _syncing = true;
    try {
      final state = _state;
      if (state == AppLifecycleState.resumed || _closed) {
        await _hide();
        return;
      }
      if (state != AppLifecycleState.paused &&
          state != AppLifecycleState.hidden) {
        return;
      }
      if (!await _relevant()) {
        await _hide();
        return;
      }
      if (!await _canShow()) {
        await _hide();
        if (!_permissionMissingReported) {
          _permissionMissingReported = true;
          SafeDiagnostics.record('pill_overlay',
              phase: 'overlay', reason: 'permission_missing');
        }
        return;
      }
      final payload = await _collect();
      final key = jsonEncode(payload);
      if (_shown) {
        if (key != _lastPayloadKey) {
          _lastPayloadKey = key;
          try {
            await _channel.invokeMethod<void>('update', payload);
          } catch (_) {/* 下一次轮询会重试。 */}
        }
        return;
      }
      try {
        await _channel.invokeMethod<void>('show', payload);
        _shown = true;
        _lastPayloadKey = key;
        _stopPoll();
        _poll = Timer.periodic(const Duration(seconds: 5), (_) {
          unawaited(_sync());
        });
      } catch (error) {
        SafeDiagnostics.record('pill_overlay',
            phase: 'overlay', reason: 'show_failed', error: error);
      }
    } catch (_) {
      // 状态读取失败时保持现状；下一轮轮询重试。
    } finally {
      _syncing = false;
    }
  }

  Future<void> _hide() async {
    if (!_shown) return;
    _shown = false;
    _lastPayloadKey = null;
    _stopPoll();
    try {
      await _channel.invokeMethod<void>('hide');
    } catch (_) {}
  }

  /// 只在"有东西值得盯着"时出现：共享活着，或本机仍持有板端链路。
  Future<bool> _relevant() async {
    try {
      return await ScreenShare.isActive() || TargetSession.hasGateway;
    } catch (_) {
      return false;
    }
  }

  Future<bool> _canShow() async {
    try {
      return await _channel.invokeMethod<bool>('canShow') == true;
    } catch (_) {
      return false;
    }
  }

  Future<Map<String, Object>> _collect() async {
    final battery = await _readBattery();
    final (share, shareText) = await _readShare();
    final (hid, hidText) = _readHid();
    final (task, taskText) = _readTask();
    final batteryDot = battery == null
        ? pillGray
        : battery < 20
            ? pillRed
            : pillGreen;
    final batteryText = battery == null ? '电量未知' : '电量 $battery%';
    final shortText = share == pillRed
        ? '共享已断开'
        : hid != pillGreen
            ? (hid == pillGray ? '未连接' : '待恢复')
            : share == pillYellow
                ? '共享检查中'
                : (battery != null && battery < 20)
                    ? '电量 $battery%'
                    : task == pillYellow
                        ? '回执滞后'
                        : '已连接';
    return {
      'battery': batteryDot,
      'share': share,
      'hid': hid,
      'task': task,
      'short': shortText,
      'line1': '$batteryText · $shareText · $hidText',
      'line2': taskText,
    };
  }

  Future<int?> _readBattery() async {
    try {
      final value = await _channel.invokeMethod<int>('battery');
      return value is int && value >= 0 && value <= 100 ? value : null;
    } catch (_) {
      return null;
    }
  }

  Future<(int, String)> _readShare() async {
    try {
      final raw = await ScreenShare.channel.invokeMethod<String>('status');
      final value = raw == null ? null : jsonDecode(raw);
      if (value is! Map) return (pillYellow, '共享检查中');
      return value['active'] == true ? (pillGreen, '共享中') : (pillRed, '共享已断开');
    } catch (_) {
      return (pillYellow, '共享检查中');
    }
  }

  (int, String) _readHid() {
    final client = TargetSession.retainedClient;
    return gatewayIndicator(
        hasClient: client != null, sessionReady: client?.authorized == true);
  }

  (int, String) _readTask() {
    final receipt = TargetSession.retainedClient?.lastReceiptAt;
    if (receipt == null) return (pillGray, '云端任务暂无回执');
    final minutes = DateTime.now().difference(receipt).inMinutes;
    if (minutes >= 10) return (pillYellow, '云端任务回执 $minutes 分钟前');
    return (pillGreen, '云端任务回执 ${minutes <= 0 ? '刚刚' : '$minutes 分钟前'}');
  }
}

final OverlayPill overlayPill = OverlayPill.instance;

/// 被控页的权限引导卡：不引入开关或持久化设置，只解释功能与引导授权。
class OverlayPillCard extends StatefulWidget {
  const OverlayPillCard({super.key});
  @override
  State<OverlayPillCard> createState() => _OverlayPillCardState();
}

class _OverlayPillCardState extends State<OverlayPillCard> {
  static const _channel = MethodChannel('pcflash/pill');
  Timer? _timer;
  bool _allowed = false, _reading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    if (defaultTargetPlatform != TargetPlatform.android) return;
    _read();
    _timer = Timer.periodic(const Duration(seconds: 2), (_) => _read());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _read() async {
    if (_reading) {
      return;
    }
    _reading = true;
    try {
      final value = await _channel.invokeMethod<bool>('canShow');
      if (mounted) {
        setState(() {
          _allowed = value == true;
          _error = null;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _error = '暂时无法读取悬浮窗权限状态，请稍后重试');
    } finally {
      _reading = false;
    }
  }

  Future<void> _settings() async {
    try {
      await _channel.invokeMethod<void>('openSettings');
    } catch (_) {
      if (mounted) {
        setState(
            () => _error = '无法打开系统设置，请从 系统 → 应用 → 手机控制助手 → 显示在其他应用上层 手动开启');
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    if (defaultTargetPlatform != TargetPlatform.android) {
      return const SizedBox.shrink();
    }
    return Card(
        child: Padding(
            padding: const EdgeInsets.all(16),
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('悬浮状态条', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              Text(_allowed
                  ? '已开启。App 退到后台且共享或链路仍在时，屏幕上角会显示电量、屏幕共享、板端链路、云端任务四个状态灯；可拖动、点按展开详情或关闭。'
                  : '尚未授权。App 退到后台且共享或链路仍在时，屏幕上角会显示上述四个状态灯，需要"显示在其他应用上层"权限。'),
              if (!_allowed) ...[
                const SizedBox(height: 8),
                OutlinedButton.icon(
                    onPressed: _settings,
                    icon: const Icon(Icons.layers_outlined),
                    label: const Text('前往系统设置开启悬浮窗权限')),
              ],
              if (_error != null)
                Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Text(_error!,
                        style: TextStyle(
                            color: Theme.of(context).colorScheme.error))),
            ])));
  }
}
