import 'controller_config.dart';
import 'dart:async';
import 'cloud_relay.dart';
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
  ControlClient({http.Client? client}) : _http = client;
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
    if (service.supportsLocalControl) _http ??= http.Client();
    if (_http == null) {
      if (!service.supportsControl) {
        throw const FormatException('请先升级控制板固件：需要蓝牙指令协议；不会改走手机直连服务器');
      }
      _board = service;
      return;
    }
    final info = await service.readInfo();
    if (info == null) throw const FormatException('请先连接控制板');
    final challenge = await _post('challenge', {'device': info.device});
    final nonce = challenge['challenge'];
    if (nonce is! String || !RegExp(r'^[0-9a-f]{64}$').hasMatch(nonce)) {
      throw const FormatException('授权挑战无效');
    }
    final bytes = Uint8List.fromList(List.generate(
        32, (i) => int.parse(nonce.substring(i * 2, i * 2 + 2), radix: 16)));
    final proof = await service.signDownloadChallenge(bytes);
    final grant = await _post('authorize', {
      'device': info.device,
      'challenge': nonce,
      'proof': proof.map((b) => b.toRadixString(16).padLeft(2, '0')).join()
    });
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
      _relayError = null;
      _relay = CloudRelay(
        post: (p, b) => _post('relay:$p', b, auth: true),
        read: service.readLocalControl,
        write: service.writeLocalControl,
        disconnect: service.disconnect,
        onError: (e) {
          _relayError = e;
        },
      );
      await _relay!.start();
    }
  }

  Future<Map<String, dynamic>> command(String operation,
      {String? text,
      String? taskId,
      String? skillId,
      Map<String, String>? parameters}) async {
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
    return _post(
        'command',
        {
          'operation': operation,
          if (text != null) 'text': text,
          if (taskId != null) 'task_id': taskId
        },
        auth: true);
  }

  void close() {
    if (_closed) return;
    _closed = true;
    final relay = _relay;
    _relay = null;
    unawaited(() async {
      try {
        if (relay != null) await relay.close();
      } finally {
        _ticket = null;
        _expires = null;
        _board = null;
        _http?.close();
      }
    }());
  }
}
