import 'dart:async';
import 'package:http/http.dart' as http;

/// BLE link establishment failed after the old task was confirmed stopped
/// and detached; nothing was written on the new link.
class BleReconnectFailure implements Exception {
  final Object cause;
  const BleReconnectFailure(this.cause);
  @override
  String toString() => '蓝牙重新连接失败：$cause';
}

/// One app-owned retry budget shared by foreground and background observers.
class GatewayRecoveryGate {
  GatewayRecoveryGate({Duration Function()? elapsed}) {
    final watch = Stopwatch()..start();
    _elapsed = elapsed ?? () => watch.elapsed;
  }
  late final Duration Function() _elapsed;
  Future<bool>? _flight;
  Duration? _next;
  int _attempts = 0, _generation = 0;
  bool _blocked = false;
  bool get exhausted => _attempts >= 3 || _blocked;
  bool get pending => _flight != null;
  String get status =>
      exhausted ? '自动恢复已停止，请重新检查手机中转；旧任务不会重发' : '连接暂时中断，正在等待安全恢复；旧任务不会重发';
  static bool transportError(Object error) =>
      error is http.ClientException || error is TimeoutException;

  Future<void> cancel() async {
    _blocked = true;
    _generation++;
    try {
      await _flight;
    } catch (_) {}
  }

  void reset() {
    if (_flight != null) throw StateError('连接恢复尚未结束');
    _generation++;
    _attempts = 0;
    _next = null;
    _blocked = false;
  }

  Future<bool> tick({
    required bool Function() eligible,
    required Future<bool> Function() guard,
    required Future<void> Function(Future<void> Function()) run,
  }) {
    if (_flight != null) return _flight!;
    if (exhausted || !eligible()) return Future.value(false);
    _next ??= _elapsed() + const Duration(seconds: 2);
    if (_elapsed() < _next!) return Future.value(false);
    final generation = _generation;
    Future<void> check() async {
      if (_blocked || generation != _generation || !await guard()) {
        throw StateError('共享或连接已结束，取消自动恢复');
      }
      if (_blocked || generation != _generation) throw StateError('连接恢复已取消');
    }

    final future = () async {
      try {
        await check();
        _attempts++;
        _next = _elapsed() + Duration(seconds: _attempts == 1 ? 4 : 8);
        await run(check);
        await check();
        _attempts = 0;
        _next = null;
        return true;
      } catch (error) {
        // Network loss and BLE link establishment share the bounded
        // 3-attempt budget; every other failure still stops auto recovery.
        if (!transportError(error) && error is! BleReconnectFailure) {
          _blocked = true;
        }
        return false;
      }
    }();
    _flight = future.whenComplete(() {
      _flight = null;
    });
    return _flight!;
  }
}
