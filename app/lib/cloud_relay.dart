import 'gateway_recovery.dart';
import 'diagnostics.dart';
import "dart:async";

/// Opaque signed packets only. No device key, action planning or ADB fallback.
class CloudRelay {
  final Future<Map<String, dynamic>> Function(String, Map<String, dynamic>)
      post;
  final Future<Map<String, dynamic>> Function() read;
  final Future<void> Function(List<int>) write;
  final Future<void> Function() disconnect;
  final void Function(Object) onError;
  final Future<void> Function(bool hid)? beforeModeChange;
  bool recoverableNetworkFailure = false;
  bool closeFinished = false;
  bool _attaching = false;
  String? get connectionNonce => _nonce;
  final String? retiredNonce;
  String _phase = 'attach';
  int? _activeOp, _activeSeq, _lastOp, _lastSeq;
  Timer? _timer;
  String? _nonce;
  DateTime? _heartbeat;
  bool _upgradeRequested = false, _maintenanceSupported = false;
  Map<String, dynamic> diagnostics = {};
  void requestWifiUpgrade() {
    if (_closed) throw StateError('网关已结束');
    _upgradeRequested = true;
  }

  bool _busy = false, _closed = false;
  CloudRelay(
      {required this.post,
      required this.read,
      required this.write,
      required this.disconnect,
      required this.onError,
      this.beforeModeChange,
      this.retiredNonce});
  bool get isClosed => _closed;
  bool get supportsMaintenance => _maintenanceSupported;

  Future<void> start({Future<void> Function()? beforePolling}) async {
    if (_closed || _timer != null) throw StateError("控制会话不可重复启动");
    final initial = await read();
    final nonce = initial["nonce"];
    if (nonce is! String || !RegExp(r"^[0-9a-f]{32}$").hasMatch(nonce)) {
      throw const FormatException("板子会话无效");
    }
    if (nonce == retiredNonce) throw const FormatException("蓝牙连接未更新，拒绝复用旧会话");
    _nonce =
        nonce; // Allows safe detach even if the attach HTTP outcome is unknown.
    _attaching = true;
    try {
      await post("attach", {"receipt": initial});
    } finally {
      _attaching = false;
      if (_closed) {
        try {
          await post('detach', {'nonce': nonce});
        } catch (_) {}
      }
    }
    _maintenanceSupported = initial.containsKey("relayOnline");
    SafeDiagnostics.record('relay_attached', phase: 'attach');
    if (_closed) throw StateError('控制连接已结束');
    await beforePolling?.call();
    if (_closed) throw StateError("控制连接已结束");
    _timer = Timer.periodic(const Duration(milliseconds: 500), (_) => _tick());
  }

  Future<void> _tick() async {
    if (_busy || _closed) return;
    _busy = true;
    try {
      final maintenance = !_maintenanceSupported
          ? null
          : _upgradeRequested
              ? 11
              : (_heartbeat == null ||
                      DateTime.now().difference(_heartbeat!).inSeconds >= 5)
                  ? 12
                  : null;
      _phase = maintenance == null ? 'poll' : 'maintenance';
      _activeOp = maintenance;
      _activeSeq = null;
      var requestClock = Stopwatch()..start();
      var command = maintenance == null
          ? await post("poll", {"nonce": _nonce})
          : await post('maintenance', {'nonce': _nonce, 'op': maintenance})
              .timeout(const Duration(seconds: 15));
      if (command["state"] == "busy") {
        _phase = 'poll';
        _activeOp = null;
        requestClock = Stopwatch()..start();
        command = await post("poll", {"nonce": _nonce});
      }
      if (_closed || command["state"] != "action") return;
      final packet = command["packet"],
          seq = command["seq"],
          op = command["op"];
      if (packet is! String ||
          !RegExp(r"^[0-9a-f]{96}$").hasMatch(packet) ||
          seq is! int ||
          op is! int ||
          op < 1 ||
          op > 14 ||
          (op > 7 && op < 11)) {
        throw const FormatException("云端动作格式无效");
      }
      _activeOp = op;
      _activeSeq = seq;
      SafeDiagnostics.record('relay_action', phase: _phase, op: op, seq: seq);
      final maintenanceAction = op == 11 || op == 12;
      final ttl = command['expiresIn'];
      if (maintenanceAction && (ttl is! int || ttl < 1 || ttl > 15)) {
        throw const FormatException('维护动作有效期无效');
      }
      final deadline = maintenanceAction ? Duration(seconds: ttl as int) : null;
      void checkActive() {
        if (_closed) throw StateError('控制连接已结束');
        if (deadline != null && requestClock.elapsed >= deadline) {
          throw TimeoutException('维护动作已过期，结果未知时不会重发');
        }
      }

      Future<T> bounded<T>(Future<T> Function() action, Duration limit) {
        checkActive();
        final remaining =
            deadline == null ? limit : deadline - requestClock.elapsed;
        if (remaining <= Duration.zero) throw TimeoutException('维护动作已过期');
        return action().timeout(remaining < limit ? remaining : limit);
      }

      checkActive();
      final bytes = List.generate(
          48, (i) => int.parse(packet.substring(i * 2, i * 2 + 2), radix: 16));
      if (op == 5 || op == 6 || op == 7) {
        _phase = 'mode';
        await beforeModeChange?.call(op == 6);
        if (_closed) return;
      }
      // Exactly one ATT write. No retry after a timeout or uncertain receipt.
      _phase = 'write';
      await bounded(() => write(bytes), const Duration(seconds: 5));
      checkActive();
      final until = requestClock.elapsed + const Duration(seconds: 10);
      _phase = 'read';
      Map<String, dynamic>? receipt;
      while (!_closed && requestClock.elapsed < until) {
        final r = await bounded(read, const Duration(seconds: 2));
        checkActive();
        diagnostics = r;
        if (r["nonce"] != _nonce) throw StateError("板子会话已改变");
        if (r["seq"] == seq &&
            r["op"] == op &&
            r["busy"] == 0 &&
            r["result"] != 1 &&
            r["result"] != 2) {
          if (op != 6 && op != 7 ||
              r["result"] != (op == 6 ? 7 : 8) ||
              r["ready"] == 1 && r["hid"] == (op == 6 ? 1 : 0)) {
            receipt = r;
            break;
          }
        }
        await bounded(
            () => Future<void>.delayed(const Duration(milliseconds: 100)),
            const Duration(milliseconds: 100));
      }
      if (receipt == null) throw TimeoutException("板端回执未确认，不会重发");
      _phase = 'ack';
      final result = await bounded(
          () => post("ack",
              {"nonce": _nonce, "id": command["id"], "receipt": receipt}),
          const Duration(seconds: 20));
      checkActive();
      if (result["state"] != "acknowledged") throw StateError("板端动作失败");
      _lastOp = op;
      _lastSeq = seq;
      SafeDiagnostics.record('relay_ack', phase: 'ack', op: op, seq: seq);
      if (op == 12) _heartbeat = DateTime.now();
      if (op == 11) _upgradeRequested = false;
      if (op == 5) await close(reason: 'opcode_stop');
    } catch (error) {
      if (_closed) return; // Late completions belong to the closed session.
      recoverableNetworkFailure = _activeSeq == null &&
          (_phase == 'poll' || _phase == 'maintenance') &&
          GatewayRecoveryGate.transportError(error);
      await close(reason: 'error', error: error);
      onError(error);
    } finally {
      _busy = false;
    }
  }

  Future<void> close({String reason = 'explicit', Object? error}) async {
    if (_closed) return;
    SafeDiagnostics.record('relay_close',
        phase: _phase,
        reason: reason,
        error: error,
        httpStatus: error is ControlHttpFailure ? error.status : null,
        op: _activeOp,
        seq: _activeSeq,
        lastOp: _lastOp,
        lastSeq: _lastSeq);
    _closed = true;
    _timer?.cancel();
    // Prepare the same-board normal-mode window before releasing our BLE owner.
    // This is best effort only; native USB/projection revocation still wins.
    if (reason == 'error' &&
        _phase != 'mode' &&
        error != null &&
        GatewayRecoveryGate.transportError(error)) {
      try {
        await beforeModeChange?.call(false).timeout(const Duration(seconds: 2));
      } catch (_) {}
    }
    // Disconnect releases HID even if cloud is unavailable.
    try {
      await disconnect();
      SafeDiagnostics.record('relay_disconnect',
          phase: 'shutdown', reason: 'disconnect_done');
    } finally {
      if (_nonce != null && !_attaching) {
        try {
          await post("detach", {"nonce": _nonce});
        } catch (_) {}
      }
      closeFinished = true;
    }
  }
}
