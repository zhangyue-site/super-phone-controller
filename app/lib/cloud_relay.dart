import 'dart:io' show Platform;
import 'gateway_recovery.dart';
import 'diagnostics.dart';
import "dart:async";
import 'package:http/http.dart' as http;
import 'relay_phase_trace.dart';
import 'ime_relay.dart';
import 'human_pill_state.dart';

/// A confirmed cloud STOP revokes only the old input session. No input retry.
class TaskRelayStopped implements Exception {
  @override
  String toString() => '旧任务已停止，等待恢复被动新任务监听';
}

class _InputHeld implements Exception {
  @override
  String toString() => '本人正在操作或输入结果待核对，原动作已停止';
}

/// Opaque signed packets only. No device key, action planning or ADB fallback.
class CloudRelay {
  final Future<Map<String, dynamic>> Function(String, Map<String, dynamic>)
      post;
  final Future<Map<String, dynamic>> Function() read;
  final Future<void> Function(List<int>) write;
  final Future<void> Function() disconnect;
  final void Function(Object) onError;
  final Future<void> Function(bool hid)? beforeModeChange;

  /// vc90 反馈闭环：动作分发/回执时回调目标坐标（共享帧空间），
  /// App 用悬浮窗在共享帧上画红/绿光标，供引擎 OCR 核验真实落点。
  final void Function(
          String phase, double x, double y, double? frameW, double? frameH)?
      onCursor;
  bool recoverableNetworkFailure = false;
  bool taskStopAcknowledged = false;
  bool closeFinished = false;
  bool _attaching = false;
  String? get connectionNonce => _nonce;
  final String? retiredNonce;
  String _phase = 'attach';
  int? _activeOp, _activeSeq, _lastOp, _lastSeq;
  Timer? _timer;
  Timer? _watchdog;
  final bool _guardAndroidInput;
  int? _remoteToken;
  (String, int, String)? _acknowledgedStop;
  final _attemptedTexts = <String>{};
  String? _nonce;
  DateTime? _heartbeat;
  DateTime? _lastControl;
  Duration? _heartbeatAt, _lastPollAt, _lastControlAt;
  late final Duration Function() _elapsed;
  bool _upgradeRequested = false, _maintenanceSupported = false;
  bool _wifiUpgradeSupported = false;
  Map<String, dynamic> diagnostics = {};
  void requestWifiUpgrade() {
    if (_closed) throw StateError('网关已结束');
    if (!supportsMaintenance) throw StateError('当前控制板请使用USB维护通道升级');
    _upgradeRequested = true;
  }

  bool _busy = false, _closed = false;
  int _pollRetryAttempt = 0;
  Duration? _pollRetryAt;
  late final RelayPhaseTrace _trace;
  CloudRelay(
      {required this.post,
      required this.read,
      required this.write,
      required this.disconnect,
      required this.onError,
      this.beforeModeChange,
      this.onCursor,
      this.retiredNonce,
      void Function(Map<String, Object>)? onTrace,
      bool tracePhases = false,
      Duration Function()? monotonic,
      bool? guardAndroidInput})
      : _guardAndroidInput = guardAndroidInput ?? Platform.isAndroid {
    final clock = Stopwatch()..start();
    _elapsed = monotonic ?? (() => clock.elapsed);
    _trace = RelayPhaseTrace(
        onEvent: onTrace ??
            (row) {
              if (!tracePhases) {
                return; // Enable only for a bounded diagnostic window.
              }
              SafeDiagnostics.record('relay_phase',
                  phase: row['phase'] as String,
                  reason: row['reason'] as String,
                  op: row['op'] as int?,
                  seq: row['seq'] as int?,
                  attempt: row['attempt'] as int,
                  stageMs: row['stage_ms'] as int,
                  writeStarted: row['write_started'] as bool,
                  failureKind: row['failure_kind'] as String?,
                  errorType: row['error_type'] as String?);
            });
  }
  bool get isClosed => _closed;

  /// Most recent confirmed receipt time (board heartbeat or control ack);
  /// null before the first receipt. Passive read for status surfaces only.
  DateTime? get lastReceiptAt {
    final hb = _heartbeat, control = _lastControl;
    if (hb != null && control != null) {
      return hb.isAfter(control) ? hb : control;
    }
    return hb ?? control;
  }

  bool get supportsMaintenance =>
      _maintenanceSupported && _wifiUpgradeSupported;

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
      HumanTapBridge.onHumanTap = () async {
        try {
          await post("human-tap", {"nonce": _nonce});
        } catch (_) {}
      };
    } finally {
      _attaching = false;
      if (_closed) {
        try {
          await post('detach', {'nonce': nonce});
        } catch (_) {}
      }
    }
    _maintenanceSupported = initial.containsKey("relayOnline");
    _wifiUpgradeSupported = initial["wifiOtaSupported"] != false;
    SafeDiagnostics.record('relay_attached', phase: 'attach');
    if (_closed) throw StateError('控制连接已结束');
    await beforePolling?.call();
    if (_closed) throw StateError("控制连接已结束");
    _lastPollAt = _elapsed(); // Keep the existing idle/startup cadence.
    _timer = Timer.periodic(const Duration(milliseconds: 100), (_) => _tick());
    _watchdog ??=
        Timer.periodic(const Duration(seconds: 5), (_) => _watchdogTick());
  }

  Future<int?> _acquireInput() async {
    final token = await ImeRelay.beginRemote();
    if (token == null) return null;
    if (_closed) {
      await ImeRelay.endRemote(token);
      return null;
    }
    _remoteToken = token;
    return token;
  }

  Future<void> _releaseInput() async {
    final token = _remoteToken;
    if (token == null) return;
    _remoteToken = null;
    await ImeRelay.endRemote(token);
  }

  Future<void> _tick() async {
    if (_busy || _closed) return;
    final now = _elapsed();
    final retryAt = _pollRetryAt;
    if (retryAt != null && now < retryAt) return;
    final fast =
        _lastControlAt != null && (now - _lastControlAt!).inMilliseconds < 3000;
    if (!fast &&
        _lastPollAt != null &&
        (now - _lastPollAt!).inMilliseconds < 500) {
      return;
    }
    _lastPollAt = now;
    _busy = true;
    var dispatched = false; // dispatch-fence
    try {
      final maintenance = !_maintenanceSupported
          ? null
          : _upgradeRequested
              ? 11
              : (_heartbeatAt == null ||
                      (_elapsed() - _heartbeatAt!).inSeconds >= 5)
                  ? 12
                  : null;
      _phase = maintenance == null ? 'poll' : 'maintenance';
      _trace.begin(_phase, op: maintenance);
      _activeOp = maintenance;
      _activeSeq = null;
      var requestClock = Stopwatch()..start();
      var command = maintenance == null
          ? await post("poll", {"nonce": _nonce})
          : await post('maintenance', {'nonce': _nonce, 'op': maintenance})
              .timeout(const Duration(seconds: 15));
              HumanPillState.updateFromReceipt(command);
      if (command["state"] == "busy") {
        _phase = 'poll';
        _trace.phase('poll', clearAction: true);
        _activeOp = null;
        requestClock = Stopwatch()..start();
        command = await post("poll", {"nonce": _nonce});
        HumanPillState.updateFromReceipt(command);
      }
      _pollRetryAttempt = 0;
      _pollRetryAt = null;
      if (_closed) return;
      if (command["state"] != "action" && command["state"] != "action_text") {
        return;
      }
      if (command["state"] == "action_text") {
        final id = command["id"],
            text = command["text"],
            op = command["op"],
            seq = command["seq"];
        if (id is! String ||
            op != 15 ||
            seq is! int ||
            text is! String ||
            text.isEmpty ||
            text.length > 64) {
          throw const FormatException("云端整句输入格式无效");
        }
        _phase = 'paste';
        _trace.phase('paste');
        _activeOp = op;
        _activeSeq = seq;
        _trace.setAction(op, seq);
        SafeDiagnostics.record('relay_paste', phase: _phase, op: op, seq: seq);
        taskStopAcknowledged = false;
        if (!_attemptedTexts.add(id)) throw _InputHeld();
        final token = _guardAndroidInput ? await _acquireInput() : null;
        if (_closed) return;
        var ok = false;
        var ownerDenied = _guardAndroidInput && token == null;
        var reason = 'paste_failed';
        if (token != null) {
          // The callback follows the editor commit. Losing it is an unknown result.
          dispatched = true;
          final outcome = await ImeRelay.pasteText(text, token);
          if (_closed) return;
          ok = outcome['ok'] == true;
          ownerDenied = !ok && outcome['reason'] == 'manual_or_busy';
          if (!ok && outcome['reason'] == 'paste_unknown') throw _InputHeld();
          // The existing cloud endpoint accepts only these failure codes.
          if (ok) {
            reason = '';
          } else if (const {
            'ime_not_authorized',
            'paste_timeout',
            'ime_switch_failed'
          }.contains(outcome['reason'])) {
            reason = outcome['reason'] as String;
          }
        }
        // Even a negative receipt must settle this already-consumed command.
        dispatched = true;
        _phase = 'ack-text';
        _trace.phase('ack');
        final ack = await post("ack-text", {
          "nonce": _nonce,
          "id": id,
          "ok": ok,
          "reason": reason,
        }).timeout(const Duration(seconds: 20));
        if (_closed) return;
        if (ack['state'] != (ok ? 'acknowledged' : 'failed')) {
          throw _InputHeld();
        }
        if (ok) {
          _lastControl = DateTime.now();
          _lastControlAt = _elapsed();
          _lastOp = op;
          _lastSeq = seq;
        }
        SafeDiagnostics.record(ok ? 'relay_ack' : 'relay_paste_rejected',
            phase: 'ack', op: op, seq: seq);
        if (ownerDenied) throw _InputHeld();
        return;
      }
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
      final stopId = command['id'];
      final stopKey = op == 5 && stopId is String && stopId.isNotEmpty
          ? (_nonce!, seq, stopId)
          : null;
      if (stopKey != null && stopKey == _acknowledgedStop) return;
      final inputAction = const {1, 2, 3, 4, 6, 13, 14}.contains(op);
      if (inputAction) {
        taskStopAcknowledged = false;
        if (_guardAndroidInput && await _acquireInput() == null) {
          throw _InputHeld();
        }
      }
      if (_closed) return;
      if (op == 5 && _guardAndroidInput) {
        // STOP must reach the board even if the optional keyboard view is gone.
        try {
          await ImeRelay.cancelVoiceForStop();
        } catch (_) {}
      }
      _activeOp = op;
      _activeSeq = seq;
      _trace.setAction(op, seq);
      SafeDiagnostics.record('relay_action', phase: _phase, op: op, seq: seq);
      // vc90 反馈闭环：动作自带目标坐标（共享帧空间）时，分发前红圈=意图坐标、
      // 板端回执后绿圈；悬浮窗画进共享帧供引擎 OCR 核验真实落点。
      // 无坐标的动作（维护/模式切换/整句文本）不画。
      final cursorX = command["x"], cursorY = command["y"];
      final cursorW = command["frameW"] ?? command["w"],
          cursorH = command["frameH"] ?? command["h"];
      void emitCursor(String phase) {
        final sink = onCursor;
        if (sink == null || cursorX is! num || cursorY is! num) return;
        sink(
            phase,
            cursorX.toDouble(),
            cursorY.toDouble(),
            cursorW is num ? cursorW.toDouble() : null,
            cursorH is num ? cursorH.toDouble() : null);
      }

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
        _trace.phase('mode');
        await beforeModeChange?.call(op == 6);
        if (_closed) return;
      }
      if (inputAction && _guardAndroidInput) {
        final token = _remoteToken;
        if (token == null || !await ImeRelay.permitsRemote(token)) {
          throw _InputHeld();
        }
        checkActive();
      }
      // Exactly one ATT write. No retry after a timeout or uncertain receipt.
      emitCursor('intent');
      _phase = 'write';
      dispatched = true; // dispatch-fence: 写出去了就不能再当"可安全重连"处理
      _trace.phase('write');
      await bounded(() {
        _trace.markWriteStarted();
        return write(bytes);
      }, const Duration(seconds: 5));
      checkActive();
      final until = requestClock.elapsed + const Duration(seconds: 10);
      _phase = 'read';
      _trace.phase('read');
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
      emitCursor('ack');
      _phase = 'ack';
      _trace.phase('ack');
      final result = await bounded(
          () => post("ack",
              {"nonce": _nonce, "id": command["id"], "receipt": receipt}),
          const Duration(seconds: 20));
      checkActive();
      if (result["state"] != "acknowledged") throw StateError("板端动作失败");
      if (const [1, 2, 3, 4, 13, 14].contains(op)) {
        _lastControl = DateTime.now();
        _lastControlAt = _elapsed();
      }
      _lastOp = op;
      _lastSeq = seq;
      SafeDiagnostics.record('relay_ack', phase: 'ack', op: op, seq: seq);
      if (op == 12) {
        _heartbeat = DateTime.now();
        _heartbeatAt = _elapsed();
      }
      if (op == 11) _upgradeRequested = false;
      if (op == 5) {
        // A STOp revokes the old input session, not the relay itself. Closing
        // here cancelled the poll timer, so no later wake/new task could ever
        // be delivered. Keep the same authenticated session polling; the next
        // poll re-adopts the board turn after the server-side STOP.
        taskStopAcknowledged = true;
        _acknowledgedStop = stopKey;
        _phase = 'poll';
        _trace.phase('poll', clearAction: true);
        _activeOp = null;
        _activeSeq = null;
        SafeDiagnostics.record('relay_task_stopped', phase: 'poll', op: op);
        return;
      }
    } catch (error) {
      if (_closed) return; // Late completions belong to the closed session.
      _trace.fail(error);
      // A transport failure before any packet is written is not a session
      // failure. Keep the relay and its timer alive and retry with a capped
      // backoff: screen-off Wi-Fi suspension must not become a detach plus a
      // permanently stopped poll loop.
      if (!dispatched && _retryablePollFailure(error)) {
        _pollRetryAttempt++;
        final delay = _pollRetryDelay(_pollRetryAttempt);
        _pollRetryAt = _elapsed() + delay;
        SafeDiagnostics.record('relay_poll_retry',
            phase: _phase,
            reason: 'transport',
            error: error,
            httpStatus: error is ControlHttpFailure ? error.status : null,
            attempt: _pollRetryAttempt,
            remainingMs: delay.inMilliseconds);
        return;
      }
      _pollRetryAttempt = 0;
      _pollRetryAt = null;
      // A lost heartbeat ACK may reconnect only through the existing STOP,
      // detach and fresh-nonce handshake. Never replay its issued packet.
      // Input or USB-mode ACK uncertainty still cannot opt into recovery.
      // dispatch-fence: 只有在"还没写出任何输入"时失败，重连才是安全的。
      // 已经写出但回执不明（ACK 网络错误等）属于 uncertain，绝不自动恢复，
      // 否则可能重复执行同一动作。授权类拒绝（relayDenial）同样走重连。
      final denial = error is ControlHttpFailure &&
          error.relayDenial &&
          !error.relayLeaseExpired;
      recoverableNetworkFailure = error is! _InputHeld &&
          _activeOp != 15 &&
          (!dispatched ||
              denial ||
              _phase ==
                  'ack'); // ackrecov: 板端回执已确认(receipt!=null 后才置 _phase='ack')，仅服务端记账不确定——恢复握手会 STOP->detach->fresh-nonce，服务端把 issued 动作置 uncertain 不再重发，故无重放风险
      await close(reason: 'error', error: error);
      onError(error);
    } finally {
      try {
        await _releaseInput();
      } finally {
        _trace.finish();
        _busy = false;
      }
    }
  }

  static Duration _pollRetryDelay(int attempt) {
    const seconds = [1, 2, 4, 8, 16, 30, 30, 30];
    final index = attempt <= 1
        ? 0
        : (attempt - 1 >= seconds.length ? seconds.length - 1 : attempt - 1);
    return Duration(seconds: seconds[index]);
  }

  /// Only failures that happen before a packet is written and that cannot be
  /// fixed by a fresh capability are retried in place. Capability denials,
  /// lease holds and validation/format failures keep their existing terminal
  /// recovery paths.
  static bool _retryablePollFailure(Object error) {
    if (error is TimeoutException || error is http.ClientException) return true;
    if (error is ControlHttpFailure) {
      return !error.relayDenial &&
          !error.relayLeaseExpired &&
          (error.status >= 500 || error.status == 408 || error.status == 429);
    }
    return false;
  }

  /// The board acks its status ping every few seconds. A long silence with
  /// the relay session still open means a BLE read/write wedged and _tick
  /// will never return on its own; force the recovery path instead of
  /// waiting for a human to restart the app.
  Future<void> _watchdogTick() async {
    if (_closed || _upgradeRequested) return;
    final hb = _heartbeatAt;
    if (hb == null) return;
    final stale = (_elapsed() - hb).inSeconds;
    if (stale <= 45) return;
    SafeDiagnostics.record('relay_watchdog',
        phase: 'stale_heartbeat', remainingMs: stale * 1000);
    recoverableNetworkFailure = true;
    await close(reason: 'stale_heartbeat');
    onError(
        TimeoutException('控制板回执 ${stale}s 未更新', const Duration(seconds: 45)));
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
    _watchdog?.cancel();
    _watchdog = null;
    await _releaseInput();
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
      // The acknowledged STOP already removed this cloud session. A late
      // detach would cancel a newly approved task on the same device.
      if (_nonce != null &&
          !_attaching &&
          !(taskStopAcknowledged && reason == 'opcode_stop')) {
        try {
          await post("detach", {"nonce": _nonce});
        } catch (_) {}
      }
      closeFinished = true;
    }
  }
}
