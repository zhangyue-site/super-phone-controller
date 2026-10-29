import 'controller_config.dart';
import 'dart:async';
import 'cloud_relay.dart';
import 'screen_share.dart';
import 'dart:convert';
import 'dart:typed_data';
import 'package:http/http.dart' as http;
import 'ble_ota_service.dart';

/// Ephemeral BLE possession capability, kept only in memory.
class ControlClient {
  static const base = '${ControllerConfig.base}/app-control';
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
  ControlClient({http.Client? client}) : _http = client;
  bool get isPaired => _paired;
  bool get supportsSkillReplay => _board != null;
  bool get canWifiUpgrade => ownsGateway && _relay?.supportsMaintenance == true;
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

  String get connectionStatus => _relayError != null
      ? '蓝牙网关已停止：$_relayError'
      : _relay != null
          ? (_relay!.isClosed ? '蓝牙网关已释放' : '此手机持有蓝牙网关；云端动作需回执确认')
          : _paired
              ? '已绑定目标；云端在线状态以任务回执为准'
              : '等待控制板授权';

  Future<void> renewCapture(String usbSession) async {
    if (!authorized || _paired || _relay == null || _ticket == null) {
      throw StateError('被控端中继未连接');
    }
    await ScreenShare.channel.invokeMethod<void>('renewCapture', {
      'controlTicket': _ticket,
      'usbSession': usbSession,
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

  Future<void> refresh() async {
    if (_closed ||
        _refreshing ||
        !authorized ||
        _expires == null ||
        _expires!.difference(DateTime.now()).inSeconds > 90) {
      return;
    }
    _refreshing = true;
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
      if (response.statusCode == 403) {
        _ticket = null;
        _expires = null;
      }
      throw FormatException(decoded['reply'] as String? ?? '请求失败，请查询状态后重试');
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
    if (service.supportsLocalControl) {
      _relayBoard = service;
      _relayError = null;
      final relay = CloudRelay(
        beforeModeChange: onModeChange,
        post: (p, b) => _post('relay:$p', b, auth: true),
        read: service.readLocalControl,
        write: service.writeLocalControl,
        disconnect: service.disconnect,
        onError: (e) {
          _relayError = e;
        },
      );
      _relay = relay;
      await relay.start();
      if (_closed) {
        await relay.close();
        checkOpen();
      }
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
    final relay = _relay;
    _relay = null;
    return _closing = () async {
      try {
        if (relay != null) await relay.close();
      } finally {
        _ticket = null;
        _expires = null;
        _board = null;
        _http?.close();
      }
    }();
  }
}
