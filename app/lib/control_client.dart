import 'diagnostics.dart';
import 'button_detector.dart';
import 'controller_config.dart';
import 'controller_pairing_store.dart';
import 'dart:async';
import 'cloud_relay.dart';
import 'gateway_recovery.dart';
import 'relay_selfheal.dart';
import 'screen_share.dart';
import 'dart:convert';
import 'dart:typed_data';
import 'package:http/http.dart' as http;
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'ble_ota_service.dart';

/// Ephemeral BLE possession capability, kept only in memory.
class ControlClient implements LocalVisionSource {
  Future<Uint8List> _localVisionBytes(
      String operation, Map<String, dynamic> body, int limit) async {
    if (!isPaired || !authorized || _http == null) {
      throw StateError('请先在控制手机连接被控手机');
    }
    final ticket = _ticket;
    final uri =
        Uri.parse('${ControllerConfig.base}/app-local-vision/$operation');
    final request = http.Request('POST', uri)..followRedirects = false;
    request.headers.addAll({
      'Authorization': 'Bearer $ticket',
      'Content-Type': 'application/json'
    });
    request.body = jsonEncode(body);
    final response =
        await _http!.send(request).timeout(const Duration(seconds: 20));
    if (response.statusCode != 200 && response.statusCode != 202) {
      await response.stream.listen((_) {}).cancel();
      if (response.statusCode == 403 && _ticket == ticket) {
        _ticket = null;
        _expires = null;
      }
      throw ControlHttpFailure(response.statusCode, '控制手机本地识别请求未获确认');
    }
    if (response.contentLength != null && response.contentLength! > limit) {
      await response.stream.listen((_) {}).cancel();
      throw const FormatException('本地识别响应过大');
    }
    final builder = BytesBuilder(copy: false);
    var count = 0;
    await for (final chunk
        in response.stream.timeout(const Duration(seconds: 30))) {
      if (_closed || _ticket != ticket || !authorized) {
        throw StateError('控制连接已结束');
      }
      count += chunk.length;
      if (count > limit) throw const FormatException('本地识别响应超过声明长度');
      builder.add(chunk);
    }
    if (_closed || _ticket != ticket || !authorized) {
      throw StateError('控制连接已结束');
    }
    return builder.takeBytes();
  }

  @override
  Future<Map<String, dynamic>> localVision(
      String operation, Map<String, dynamic> body) async {
    if (!const ['manifest', 'frame', 'result'].contains(operation)) {
      throw ArgumentError('本地识别操作无效');
    }
    final raw = await _localVisionBytes(
        operation, body, operation == 'frame' ? 750000 : 8192);
    final value = jsonDecode(utf8.decode(raw));
    if (value is! Map<String, dynamic>) {
      throw const FormatException('本地识别响应格式无效');
    }
    return value;
  }

  @override
  Future<Uint8List> localModelBytes(ButtonModelManifest manifest) async {
    final raw = await _localVisionBytes(
        'model', {'sha256': manifest.sha256}, manifest.size);
    if (raw.length != manifest.size) throw const FormatException('模型下载长度不符');
    return raw;
  }

  static String get base => '${ControllerConfig.base}/app-control';
  http.Client? _http;
  CloudRelay? _relay;
  bool _closed = false;
  Object? _relayError;
  BleOtaService? _board;
  String? _ticket;
  DateTime? _expires;
  BleOtaService? _relayBoard;
  bool _paired = false, _refreshing = false;
  Future<void>? _closing;
  String? deviceId;
  Future<void> Function(bool hid)? onModeChange;

  // Self-heal (vc60). Bounded in-place re-authorization after a relay
  // capability denial. See RelaySelfHeal for the retry contract.
  bool _healing = false, _healExhausted = false;
  int _healAttempts = 0;
  String? _healReason;
  Timer? _healTimer, _healWatch;
  String? _boardRemoteId;
  final Duration Function(int attempt) _healDelay;
  ControlClient({http.Client? client, Duration Function(int attempt)? healDelay})
      : _http = client,
        _healDelay = healDelay ?? RelaySelfHeal.delayBefore;
  @override
  bool get isPaired => _paired;
  bool get supportsSkillReplay => _board != null;
  bool get canWifiUpgrade => ownsGateway && _relay?.supportsMaintenance == true;
  bool get usesBoardLink => _board != null || _relayBoard != null;
  bool get ownsGateway => _relay != null && authorized;
  String get upgradeStatus {
    final stage = _relay?.diagnostics['otaStage'];
    return switch (stage) {
      1 => '正在检查 Wi-Fi 固件',
      2 => '正在写入固件',
      3 => '板端准备重启，需重新连接核验版本',
      4 => '板端报告已是当前版本',
      5 => 'Wi-Fi 升级失败，请检查网络或使用蓝牙升级/USB救援',
      _ => '升级状态尚未确认'
    };
  }

  void requestWifiUpgrade() {
    if (!ownsGateway) throw StateError('仅当前蓝牙网关可请求板端 Wi-Fi 升级');
    _relay!.requestWifiUpgrade();
  }

  String get connectionStatus => _healing
      ? '中继授权失效，正在自动重连（第 $_healAttempts/${RelaySelfHeal.maxAttempts} 次）'
      : _healExhausted && _relayError != null
          ? '自动重连已停止（${_healReason ?? '授权失效'}）；请重新连接控制板'
          : _relayError != null
              ? '蓝牙网关已停止：$_relayError'
              : _relay != null
                  ? (_relay!.isClosed ? '蓝牙网关已释放' : '此手机持有蓝牙网关；云端动作需回执确认')
                  : _paired
                      ? '已绑定目标；云端在线状态以任务回执为准'
                      : '等待控制板授权';

  /// Non-null while a bounded self-heal is running or after it gave up, so
  /// the target screens can show the real reason instead of "re-pair".
  String? get selfHealStatus => _healing
      ? '中继授权失效，正在自动重连（第 $_healAttempts/${RelaySelfHeal.maxAttempts} 次）'
      : _healExhausted
          ? '自动重连已停止（${_healReason ?? '授权失效'}）；请重新连接控制板'
          : null;
  bool get selfHealing => _healing;
  bool get selfHealExhausted => _healExhausted;
  int get selfHealAttempts => _healAttempts;

  Future<void> renewCapture([String? usbSession]) async {
    if (!authorized || _paired || _relay == null || _ticket == null) {
      throw StateError('被控端中继未连接');
    }
    await ScreenShare.channel.invokeMethod<void>('renewCapture', {
      'controlTicket': _ticket,
      if (usbSession != null) 'usbSession': usbSession,
    });
  }

  Future<void> pair(String code) async {
    if (_closed ||
        _ticket != null ||
        !RegExp(r'^[A-Za-z0-9_-]{43}$').hasMatch(code)) {
      throw const FormatException('请粘贴被控手机生成的完整连接码');
    }
    _http ??= http.Client();
    final grant = await _post('pair-redeem', {'code': code});
    final ticket = grant['ticket'], device = grant['device'];
    if (_closed ||
        grant['scope'] != 'phone-commands' ||
        ticket is! String ||
        !RegExp(r'^[A-Za-z0-9_-]{43}$').hasMatch(ticket) ||
        device is! String ||
        !RegExp(r'^[A-Za-z0-9_-]{1,64}$').hasMatch(device) ||
        grant['expiresIn'] != 300) {
      throw const FormatException('连接授权无效');
    }
    _paired = true;
    _ticket = ticket;
    deviceId = device;
    _expires = DateTime.now().add(const Duration(seconds: 300));
  }

  ControllerPairing? get restorablePairing {
    final ticket = _ticket, device = deviceId, expires = _expires;
    if (!_paired ||
        !authorized ||
        ticket == null ||
        device == null ||
        expires == null) {
      return null;
    }
    return ControllerPairing(ticket, device, expires);
  }

  Future<void> restorePairing(ControllerPairing pairing) async {
    if (_closed || _ticket != null || !pairing.valid) {
      throw StateError('配对已失效');
    }
    _http ??= http.Client();
    _paired = true;
    _ticket = pairing.ticket;
    deviceId = pairing.device;
    _expires = pairing.expires;
    try {
      await _refresh(force: true);
      if (!authorized) throw StateError('配对已失效');
    } catch (_) {
      _ticket = null;
      _expires = null;
      _paired = false;
      deviceId = null;
      rethrow;
    }
  }

  Future<Map<String, dynamic>> pairingCode() async {
    if (!authorized || _paired || _relay == null) {
      throw StateError('请先建立被控手机中继');
    }
    return _post('pair-issue', {}, auth: true);
  }

  Future<void> revokeControllers() async {
    if (!canReadStatus || _paired) throw StateError('被控端连接已结束');
    await _post('pair-revoke', {}, auth: true);
  }

  Future<void> refresh() => _refresh();

  Future<void> _refresh({bool force = false}) async {
    if (_closed ||
        _refreshing ||
        !authorized ||
        _expires == null ||
        (!force && _expires!.difference(DateTime.now()).inSeconds > 90)) {
      return;
    }
    _refreshing = true;
    SafeDiagnostics.record('control_refresh',
        phase: 'renew',
        reason: 'renew_begin',
        remainingMs: _expires?.difference(DateTime.now()).inMilliseconds);
    try {
      Map<String, dynamic> result;
      if (_paired) {
        result = await _post('pair-renew', {}, auth: true);
      } else {
        final board = _relayBoard;
        if (board == null) return;
        final info = await board.readInfo();
        if (info == null || info.device != deviceId) {
          throw StateError('控制板身份已改变');
        }
        final challenge = await _post('challenge', {'device': info.device});
        final nonce = challenge['challenge'];
        if (nonce is! String || !RegExp(r'^[0-9a-f]{64}$').hasMatch(nonce)) {
          throw const FormatException('授权挑战无效');
        }
        final proof = await board.signDownloadChallenge(Uint8List.fromList(
            List.generate(
                32,
                (i) =>
                    int.parse(nonce.substring(i * 2, i * 2 + 2), radix: 16))));
        result = await _post(
            'renew',
            {
              'device': info.device,
              'challenge': nonce,
              'proof':
                  proof.map((b) => b.toRadixString(16).padLeft(2, '0')).join()
            },
            auth: true);
      }
      if (result['scope'] != 'phone-commands' || result['expiresIn'] != 300) {
        throw const FormatException('续期授权无效');
      }
      if (!_closed) _expires = DateTime.now().add(const Duration(seconds: 300));
      SafeDiagnostics.record('control_refresh',
          phase: 'renew',
          reason: 'renew_ok',
          remainingMs: _expires?.difference(DateTime.now()).inMilliseconds);
    } catch (e) {
      SafeDiagnostics.record('control_refresh',
          phase: 'renew',
          reason: 'renew_fail',
          error: e,
          httpStatus: e is ControlHttpFailure ? e.status : null);
      rethrow;
    } finally {
      _refreshing = false;
    }
  }

  bool get canReadStatus =>
      !_closed &&
      (_board != null ||
          (_ticket != null &&
              _expires != null &&
              DateTime.now().isBefore(_expires!)));
  @override
  bool get authorized =>
      canReadStatus &&
      _relayError == null &&
      (_relay == null || !_relay!.isClosed);
  Future<Map<String, dynamic>> _post(String path, Map<String, dynamic> body,
      {bool auth = false}) async {
    final response = await _http!
        .post(
            Uri.parse(path.startsWith('relay:')
                ? "${base.replaceFirst('/app-control', '/app-relay')}/${path.substring(6)}"
                : '$base/$path'),
            headers: {
              'Content-Type': 'application/json',
              if (auth) 'Authorization': 'Bearer $_ticket',
            },
            body: jsonEncode(body))
        .timeout(const Duration(seconds: 20));
    if (response.bodyBytes.length > 8192) {
      throw const FormatException('服务器响应过大');
    }
    final decoded = jsonDecode(utf8.decode(response.bodyBytes));
    if (decoded is! Map<String, dynamic>) {
      throw const FormatException('服务器响应无效');
    }
    if (response.statusCode != 200) {
      SafeDiagnostics.record('control_http_failure',
          phase: path.startsWith('relay:') ? path.substring(6) : path,
          reason: 'http_error',
          httpStatus: response.statusCode);
      // Only an authenticated lease expiry before delivery may recover.
      // Generic 403 and uncertain action ACKs remain terminal.
      if (response.statusCode == 409 &&
          (path == 'relay:poll' || path == 'relay:maintenance') &&
          decoded['code'] == 'relay_lease_expired') {
        throw ControlHttpFailure(409, '中转连接过期，停止旧任务后重新连接',
            relayLeaseExpired: true);
      }
      if (response.statusCode == 403 && path != 'relay:detach') {
        _ticket = null;
        _expires = null;
      }
      final relayPath = path.startsWith('relay:');
      final reply = decoded['reply'];
      final code = decoded['code']?.toString();
      // A relay data path denied for a capability reason (401/403, or a
      // reply/code naming a lease, expiry or ticket) may re-authorize in
      // place. detach and every non-relay path keep their exact meaning.
      final denial = relayPath &&
          path != 'relay:detach' &&
          (response.statusCode == 401 ||
              response.statusCode == 403 ||
              RelaySelfHeal.denialText(reply is String ? reply : null) ||
              RelaySelfHeal.denialText(code));
      throw ControlHttpFailure(
          response.statusCode,
          reply as String? ??
              (response.statusCode == 401 || response.statusCode == 403
                  ? '中继授权已失效，正在重新授权'
                  : '请求失败，请查询状态后重试'),
          relayDenial: denial);
    }
    return decoded;
  }

  Future<void> authorize(BleOtaService service) async {
    void checkOpen() {
      if (_closed) throw StateError('控制连接已结束');
    }

    checkOpen();
    if (service.supportsLocalControl) _http ??= http.Client();
    if (_http == null) {
      if (!service.supportsControl) {
        throw const FormatException('请先升级控制板固件：需要蓝牙指令协议；不会改走手机直连服务器');
      }
      _board = service;
      return;
    }
    final info = await service.readInfo();
    checkOpen();
    if (info == null) throw const FormatException('请先连接控制板');
    deviceId = info.device;
    _boardRemoteId = service.device?.remoteId.str ?? _boardRemoteId;
    final challenge = await _post('challenge', {'device': info.device});
    checkOpen();
    final nonce = challenge['challenge'];
    if (nonce is! String || !RegExp(r'^[0-9a-f]{64}$').hasMatch(nonce)) {
      throw const FormatException('授权挑战无效');
    }
    final bytes = Uint8List.fromList(List.generate(
        32, (i) => int.parse(nonce.substring(i * 2, i * 2 + 2), radix: 16)));
    final proof = await service.signDownloadChallenge(bytes);
    checkOpen();
    final grant = await _post('authorize', {
      'device': info.device,
      'challenge': nonce,
      'proof': proof.map((b) => b.toRadixString(16).padLeft(2, '0')).join()
    });
    checkOpen();
    final ticket = grant['ticket'];
    final ttl = grant['expiresIn'];
    if (grant['scope'] != 'phone-commands' ||
        ticket is! String ||
        !RegExp(r'^[A-Za-z0-9_-]{43}$').hasMatch(ticket) ||
        ttl is! int ||
        ttl < 1 ||
        ttl > 300) {
      throw const FormatException('授权范围无效');
    }
    _ticket = ticket;
    _expires = DateTime.now().add(Duration(seconds: ttl));
    SafeDiagnostics.record('control_grant',
        phase: 'authorize', reason: 'grant_ok', remainingMs: ttl * 1000);
    if (service.supportsLocalControl) {
      _relayBoard = service;
      _relayError = null;
      _healExhausted = false;
      _healAttempts = 0;
      final relay = CloudRelay(
        beforeModeChange: onModeChange,
        post: (p, b) => _post('relay:$p', b, auth: true),
        read: service.readLocalControl,
        write: service.writeLocalControl,
        disconnect: service.disconnect,
        onError: _relayErrorSink,
      );
      _relay = relay;
      await relay.start();
      if (_closed) {
        await relay.close();
        checkOpen();
      }
      _startHealWatch();
    }
  }

  /// Every relay failure enters here once. Only a capability denial starts a
  /// bounded re-authorization; anything else keeps the old terminal stop.
  void _relayErrorSink(Object error) {
    if (_closed) return;
    _relayError = error;
    _stopHealWatch();
    if (RelaySelfHeal.permissionError(error)) _beginSelfHeal(error);
  }

  DateTime? _lastHealAt;
  Timer? _healResetTimer;

  void _beginSelfHeal(Object cause) {
    if (_closed || _paired || _relayBoard == null || _healing) return;
    final now = DateTime.now();
    final continuing = _lastHealAt != null &&
        now.difference(_lastHealAt!) < const Duration(seconds: 5);
    _healing = true;
    _healExhausted = false;
    if (!continuing) _healAttempts = 0;
    _healReason = RelaySelfHeal.reasonText(cause);
    SafeDiagnostics.record('relay_selfheal',
        phase: 'attach',
        reason: 'begin',
        httpStatus: cause is ControlHttpFailure ? cause.status : null);
    _scheduleHealAttempt();
  }

  void _scheduleHealAttempt() {
    _healTimer?.cancel();
    final attempt = _healAttempts + 1;
    if (_closed || attempt > RelaySelfHeal.maxAttempts) {
      _finishSelfHeal();
      return;
    }
    _healAttempts = attempt;
    final delay = _healDelay(attempt);
    _healTimer = Timer(delay, () {
      _healTimer = null;
      if (!_closed && _healing) unawaited(_healOnce());
    });
  }

  Future<void> _healOnce() async {
    final board = _relayBoard;
    if (board == null) {
      _finishSelfHeal();
      return;
    }
    try {
      _relayError = null; // 清掉旧错误，下面的存活检查才有意义
      await _reauthAndAttach(board);
      if (_closed) return;
      // healverify: 重连必须真的活了才算成功。CloudRelay 可能只把错误交给
      // onError 而不抛异常，这里必须自己核对，否则会假装恢复、永不计满预算。
      final relay = _relay;
      if (_relayError != null || relay == null || relay.isClosed) {
        throw StateError('重新授权后中继仍未建立');
      }
      _healing = false;
      _lastHealAt = DateTime.now();
      _healReason = null;
      _healExhausted = false;
      _relayError = null;
      _startHealWatch();
      // 计数不在这里清零：中继刚 attach 完最可能马上又被拒，清零会让重试
      // 永远停在第 1 次、预算永远计不满。等 30 秒安静后再归零。
      _healResetTimer?.cancel();
      _healResetTimer = Timer(const Duration(seconds: 30), () {
        if (_closed || _healing) return;
        _healAttempts = 0;
      });
      SafeDiagnostics.record('relay_selfheal', phase: 'poll', reason: 'recovered');
    } catch (error) {
      if (_closed) return;
      _healReason = RelaySelfHeal.reasonText(error);
      SafeDiagnostics.record('relay_selfheal',
          phase: 'attach',
          reason: 'retry',
          error: error,
          attempt: _healAttempts,
          httpStatus: error is ControlHttpFailure ? error.status : null);
      if (!RelaySelfHeal.retryable(error)) {
        _healAttempts = RelaySelfHeal.maxAttempts; // terminal, no more tries
        _finishSelfHeal();
        return;
      }
      if (_healAttempts >= RelaySelfHeal.maxAttempts) {
        _finishSelfHeal();
        return;
      }
      _scheduleHealAttempt();
    }
  }

  void _finishSelfHeal() {
    _healResetTimer?.cancel();
    _healTimer?.cancel();
    _healTimer = null;
    _healing = false;
    _healExhausted = true;
    _relayError ??= _healReason;
    SafeDiagnostics.record('relay_selfheal',
        phase: 'idle', reason: 'exhausted', attempt: _healAttempts);
  }

  /// The control ticket can also lapse while the relay is still polling (an
  /// idle UI never calls refresh). Re-authorize before the next poll denies.
  void _startHealWatch() {
    if (_closed || _healWatch != null || _paired || _relayBoard == null) return;
    _healWatch = Timer.periodic(const Duration(seconds: 1), (_) {
      final relay = _relay;
      if (_closed || relay == null || relay.isClosed || _healing) {
        _stopHealWatch();
        return;
      }
      final expires = _expires;
      if (expires == null || DateTime.now().isBefore(expires)) return;
      _stopHealWatch();
      _beginSelfHeal(ControlHttpFailure(401, 'ticket expired', relayDenial: true));
    });
  }

  void _stopHealWatch() {
    _healWatch?.cancel();
    _healWatch = null;
  }

  /// Re-opens the same physical board after the failed relay released BLE.
  /// Only the identity observed at authorize/recovery time is reused; without
  /// one (pure tests, or a link the platform still holds) nothing is invented.
  Future<void> _ensureBoardLink(BleOtaService board) async {
    final id = _boardRemoteId;
    if (id == null) return;
    final device = board.device;
    if (device != null && device.remoteId.str == id && device.isConnected) {
      return;
    }
    try {
      await board.connect(BluetoothDevice.fromId(id));
    } on StateError {
      rethrow;
    } catch (error) {
      throw BleReconnectFailure(error);
    }
  }

  /// challenge -> authorize (full handshake, not renew: an invalidated ticket
  /// cannot renew itself) -> fresh attach receipt -> poll resumes.
  Future<void> _reauthAndAttach(BleOtaService board) async {
    void checkOpen() {
      if (_closed) throw StateError('控制连接已结束');
    }

    checkOpen();
    final old = _relay;
    _relay = null;
    _stopHealWatch();
    if (old != null) {
      try {
        await old.close(reason: 'self_heal');
      } catch (_) {/* detach may itself be denied; the server lease expires. */}
    }
    checkOpen();
    // The failed relay already released BLE, so the same board has to be
    // re-opened before any challenge can be signed.
    await _ensureBoardLink(board);
    checkOpen();
    final info = await board.readInfo();
    checkOpen();
    if (info == null || info.device != deviceId) {
      throw StateError('控制板身份已改变，自动重连已停止');
    }
    final challenge = await _post('challenge', {'device': info.device});
    checkOpen();
    final nonce = challenge['challenge'];
    if (nonce is! String || !RegExp(r'^[0-9a-f]{64}$').hasMatch(nonce)) {
      throw const FormatException('授权挑战无效');
    }
    final proof = await board.signDownloadChallenge(Uint8List.fromList(
        List.generate(
            32, (i) => int.parse(nonce.substring(i * 2, i * 2 + 2), radix: 16))));
    checkOpen();
    if (proof.length != 32) {
      throw const FormatException('控制板授权证明无效');
    }
    final grant = await _post('authorize', {
      'device': info.device,
      'challenge': nonce,
      'proof': proof.map((b) => b.toRadixString(16).padLeft(2, '0')).join()
    });
    checkOpen();
    final ticket = grant['ticket'], ttl = grant['expiresIn'];
    if (grant['scope'] != 'phone-commands' ||
        ticket is! String ||
        !RegExp(r'^[A-Za-z0-9_-]{43}$').hasMatch(ticket) ||
        ttl is! int ||
        ttl < 1 ||
        ttl > 300) {
      throw const FormatException('授权范围无效');
    }
    _ticket = ticket;
    _expires = DateTime.now().add(Duration(seconds: ttl));
    _relayError = null;
    SafeDiagnostics.record('control_grant',
        phase: 'authorize', reason: 'grant_ok', remainingMs: ttl * 1000);
    // Same physical session, same nonce: the server adopts it in place.
    final next = CloudRelay(
      beforeModeChange: onModeChange,
      post: (p, b) => _post('relay:$p', b, auth: true),
      read: board.readLocalControl,
      write: board.writeLocalControl,
      disconnect: board.disconnect,
      onError: _relayErrorSink,
    );
    _relay = next;
    try {
      await next.start();
    } catch (_) {
      _relay = null;
      try {
        await next.close(reason: 'self_heal');
      } catch (_) {}
      rethrow;
    }
    checkOpen();
    // Screen capture has its own capability; renew it with the new control
    // ticket only while a capture is actually live. Failure here is not fatal.
    try {
      if (await ScreenShare.isActive()) await renewCapture();
    } catch (_) {}
    checkOpen();
  }

  bool get canRecoverGateway =>
      !_closed &&
      !_paired &&
      canReadStatus &&
      _relayBoard != null &&
      _relay?.isClosed == true &&
      _relay?.closeFinished == true &&
      _relay?.recoverableNetworkFailure == true;
  bool get gatewayRecoveryNeedsPairing =>
      !_closed && _relay?.recoverableNetworkFailure == true && !canReadStatus;

  Future<void> recoverGateway(
      {required Future<void> Function() reconnect,
      required Future<void> Function() check}) async {
    if (!canRecoverGateway) throw StateError('自动恢复条件不满足');
    final oldRelay = _relay!;
    final board = _relayBoard!, retired = oldRelay.connectionNonce;
    Future<void> current() async {
      if (_closed || !canReadStatus) throw StateError('授权已过期，请重新连接并配对控制手机');
      await check();
      if (_closed || !canReadStatus) throw StateError('连接恢复已取消');
    }

    var connected = false;
    CloudRelay? next;
    try {
      await current();
      // Reconcile the old task before any new BLE handshake. Never replay a packet.
      final stopped = await command('stop');
      await current();
      if (stopped['state'] != 'stopped') throw StateError('旧任务停止尚未确认');
      if (retired != null) {
        try {
          await _post('relay:detach', {'nonce': retired}, auth: true);
        } on ControlHttpFailure catch (error) {
          if (error.status != 403) rethrow;
        }
      }
      await current();
      // reconnect() may open BLE and then fail its trailing check(); from
      // here on this owner disconnects whatever link it may have opened.
      connected = true;
      await reconnect();
      await current();
      final info = await board.readInfo();
      await current();
      if (info == null ||
          info.device != deviceId ||
          !board.supportsLocalControl) {
        throw StateError('控制板身份或协议已改变，自动恢复已停止');
      }
      _boardRemoteId = board.device?.remoteId.str ?? _boardRemoteId;
      final challenge = await _post('challenge', {'device': info.device});
      await current();
      final nonce = challenge['challenge'];
      if (nonce is! String || !RegExp(r'^[0-9a-f]{64}$').hasMatch(nonce)) {
        throw const FormatException('授权挑战无效');
      }
      final proof = await board.signDownloadChallenge(Uint8List.fromList(
          List.generate(32,
              (i) => int.parse(nonce.substring(i * 2, i * 2 + 2), radix: 16))));
      await current();
      if (proof.length != 32) {
        throw const FormatException('控制板授权证明无效');
      }
      final result = await _post(
          'renew',
          {
            'device': info.device,
            'challenge': nonce,
            'proof':
                proof.map((b) => b.toRadixString(16).padLeft(2, '0')).join()
          },
          auth: true);
      await current();
      if (result['scope'] != 'phone-commands' || result['expiresIn'] != 300) {
        throw const FormatException('续期授权无效');
      }
      _expires = DateTime.now().add(const Duration(seconds: 300));
      next = CloudRelay(
        retiredNonce: retired,
        beforeModeChange: onModeChange,
        post: (p, b) => _post('relay:$p', b, auth: true),
        read: board.readLocalControl,
        write: board.writeLocalControl,
        disconnect: board.disconnect,
        onError: _relayErrorSink,
      );
      _relay = next;
      await next.start(beforePolling: current);
      if (_closed) throw StateError('连接恢复已取消');
      _relayError = null;
      _healing = false;
      _healExhausted = false;
      _healAttempts = 0;
      _healReason = null;
      _startHealWatch();
    } catch (_) {
      if (!_closed) _relay = oldRelay;
      if (next != null) {
        await next.close(reason: 'owner_shutdown');
      } else if (connected) {
        await board.disconnect();
      }
      rethrow;
    }
  }

  Future<Map<String, dynamic>> command(String operation,
      {String? text,
      String? taskId,
      String? skillId,
      Map<String, String>? parameters}) async {
    if ((operation == 'skills' || operation == 'skill') &&
        !supportsSkillReplay) {
      throw UnsupportedError('技能回放暂未接通；已保存数据不会删除，可继续发送普通文字任务');
    }
    final readOrStop = operation == 'status' || operation == 'stop';
    if (!(readOrStop ? canReadStatus : authorized)) {
      throw const FormatException('控制连接已结束，请返回并重新连接控制板；旧动作不会重发');
    }
    final body = <String, dynamic>{
      'operation': operation,
      if (text != null) 'text': text,
      if (taskId != null) 'task_id': taskId,
      if (skillId != null) 'skill_id': skillId,
      if (parameters != null) 'parameters': parameters
    };
    if (_board != null) return _board!.controlRequest(body);
    return _post('command', {...body}, auth: true);
  }

  void close() => unawaited(shutdown());

  Future<void> shutdown() {
    if (_closing != null) return _closing!;
    _closed = true;
    _healing = false;
    _healTimer?.cancel();
    _healTimer = null;
    _stopHealWatch();
    final relay = _relay;
    _relay = null;
    return _closing = () async {
      try {
        if (relay != null) await relay.close(reason: 'owner_shutdown');
      } finally {
        _ticket = null;
        _expires = null;
        _board = null;
        _http?.close();
      }
    }();
  }
}
