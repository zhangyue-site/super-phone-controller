import 'dart:convert';
import 'dart:typed_data';
import 'package:crypto/crypto.dart';
import 'package:http/http.dart' as http;
import 'firmware_image.dart';

class DownloadedFirmware {
  final Uint8List bytes;
  final String version;
  final String? ticket;
  final DateTime? expiresAt;
  const DownloadedFirmware(this.bytes, this.version,
      {this.ticket, this.expiresAt});
}

class OfficialFirmwareRelease {
  final String version, sha256;
  final int size;
  final bool current;
  const OfficialFirmwareRelease(
      this.version, this.sha256, this.size, this.current);
}

class AppOtaException implements Exception {
  final String stage;
  final int statusCode;
  const AppOtaException(this.stage, this.statusCode);
  @override
  String toString() {
    final advice = statusCode == 429
        ? '请求过于频繁，请稍后手动重试'
        : statusCode == 401 || statusCode == 410
            ? '凭证已失效，请重新下载官方固件并再次确认刷写'
            : statusCode == 403
                ? '服务拒绝授权；可能是凭证过期或校验未通过。请重新下载官方固件；仍失败请提供此阶段和状态码'
                : '升级服务暂时不可用，请稍后手动重试';
    return '$stage失败（HTTP $statusCode）：$advice';
  }
}

class AppOtaClient {
  final Uri base;
  final http.Client _client;
  final bool _ownsClient;
  AppOtaClient(this.base, {http.Client? client})
      : _client = client ?? http.Client(),
        _ownsClient = client == null {
    if (base.scheme != 'https') throw ArgumentError('HTTPS required');
  }
  void close() {
    if (_ownsClient) _client.close();
  }

  Uri _uri(String path) => Uri.parse(
      "${base.toString().replaceFirst(RegExp(r'/$'), '')}/app-ota/$path");
  Future<Map<String, dynamic>> _post(String path, Map<String, dynamic> body,
      {String? ticket}) async {
    final response = await _client
        .post(_uri(path),
            headers: {
              'Content-Type': 'application/json',
              if (ticket != null) 'Authorization': 'Bearer $ticket'
            },
            body: jsonEncode(body))
        .timeout(const Duration(seconds: 25));
    if (response.statusCode != 200) {
      throw AppOtaException(
          const {
                'challenge': '获取升级挑战',
                'authorize': '固件下载授权',
                'ble-authorize': '蓝牙刷写授权',
                'releases': '官方版本列表'
              }[path] ??
              '升级请求',
          response.statusCode);
    }
    if (response.bodyBytes.length > 4096) {
      throw const FormatException('升级服务响应过大');
    }
    final dynamic obj = jsonDecode(response.body);
    if (obj is! Map<String, dynamic>) throw const FormatException('升级服务响应无效');
    return obj;
  }

  Future<List<int>> authorizeBle(String ticket, String device, String boot,
      List<int> challenge, Future<List<int>> Function(List<int>) sign,
      {String protocol = 'hmac-sha256-v1'}) async {
    final imageBound = protocol == 'hmac-sha256-image-v2';
    if (!imageBound && protocol != 'hmac-sha256-v1') {
      throw const FormatException('升级授权协议不受支持');
    }
    if (challenge.length != 32) throw const FormatException('蓝牙升级挑战无效');
    String hex(List<int> bytes) =>
        bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
    final proof = await sign(challenge);
    if (proof.length != 32) throw const FormatException('控制板升级授权响应无效');
    final result = await _post(
        'ble-authorize',
        {
          'device': device,
          'boot': boot,
          'challenge': hex(challenge),
          'proof': hex(proof),
        },
        ticket: ticket);
    final authorization = result['authorization'];
    final ttl = result['expiresIn'];
    if (result['scope'] != 'ble-ota' ||
        ttl is! int ||
        ttl < 1 ||
        ttl > 60 ||
        authorization is! String ||
        !RegExp(imageBound ? r'^[0-9a-f]{200}$' : r'^[0-9a-f]{64}$')
            .hasMatch(authorization) ||
        (imageBound && result['protocol'] != protocol)) {
      throw const FormatException('蓝牙升级授权无效');
    }
    return List.generate(imageBound ? 100 : 32,
        (i) => int.parse(authorization.substring(i * 2, i * 2 + 2), radix: 16));
  }

  Future<List<OfficialFirmwareRelease>> releases(String ticket) async {
    final response = await _post('releases', {}, ticket: ticket);
    final entries = response['releases'];
    if (entries is! List || entries.isEmpty || entries.length > 20) {
      throw const FormatException('官方版本列表无效');
    }
    final result = <OfficialFirmwareRelease>[];
    final seen = <String>{};
    for (final entry in entries) {
      if (entry is! Map ||
          entry['version'] is! String ||
          !RegExp(r'^[A-Za-z0-9._-]{1,31}$').hasMatch(entry['version']) ||
          entry['sha256'] is! String ||
          !RegExp(r'^[0-9a-f]{64}$').hasMatch(entry['sha256']) ||
          entry['size'] is! int ||
          entry['size'] < 4096 ||
          entry['size'] > 0x600000 ||
          entry['current'] is! bool ||
          !seen.add(entry['sha256'])) {
        throw const FormatException('官方版本条目无效');
      }
      result.add(OfficialFirmwareRelease(
          entry['version'], entry['sha256'], entry['size'], entry['current']));
    }
    if (result.where((r) => r.current).length != 1) {
      throw const FormatException('官方当前版本无效');
    }
    return result;
  }

  Future<DownloadedFirmware> download(
      String device, Future<List<int>> Function(List<int>) sign,
      {String? boardModel,
      String? selectedSha,
      bool Function()? isActive}) async {
    void checkActive() {
      if (isActive != null && !isActive()) throw StateError('固件下载已取消，请手动重新开始');
    }

    checkActive();
    if (selectedSha != null &&
        !RegExp(r"^[0-9a-f]{64}$").hasMatch(selectedSha)) {
      throw const FormatException("所选官方固件摘要无效");
    }
    final maxSize = boardModel == 'esp32-s3-touch-amoled-2.16'
        ? 0x600000
        : FirmwareImage.maxSize;
    final challenge = await _post('challenge', {'device': device});
    checkActive();
    final nonce = challenge['challenge'];
    if (nonce is! String || !RegExp(r'^[0-9a-f]{64}$').hasMatch(nonce)) {
      throw const FormatException('升级挑战无效');
    }
    final raw = List.generate(
        32, (i) => int.parse(nonce.substring(i * 2, i * 2 + 2), radix: 16));
    final proof = await sign(raw);
    if (proof.length != 32) throw const FormatException('控制板升级授权响应无效');
    checkActive();
    final grant = await _post('authorize', {
      'device': device,
      'challenge': nonce,
      if (selectedSha != null) 'sha256': selectedSha,
      'proof': proof.map((b) => b.toRadixString(16).padLeft(2, '0')).join()
    });
    checkActive();
    final grantedAt = DateTime.now();
    final size = grant['size'],
        digest = grant['sha256'],
        version = grant['version'],
        ticket = grant['ticket'];
    if (size is! int ||
        size < 4096 ||
        size > maxSize ||
        digest is! String ||
        !RegExp(r'^[0-9a-f]{64}$').hasMatch(digest) ||
        version is! String ||
        !RegExp(r'^[A-Za-z0-9._-]{1,31}$').hasMatch(version) ||
        ticket is! String ||
        !RegExp(r'^[A-Za-z0-9_-]{43}$').hasMatch(ticket)) {
      throw const FormatException('固件下载凭证无效');
    }
    if (selectedSha != null && digest != selectedSha) {
      throw const FormatException('服务授权镜像与所选官方版本不符');
    }
    checkActive();
    final request = http.Request('GET', _uri('image'));
    request.headers['Authorization'] = 'Bearer $ticket';
    final response =
        await _client.send(request).timeout(const Duration(seconds: 25));
    checkActive();
    if (response.statusCode != 200) {
      throw AppOtaException('固件下载', response.statusCode);
    }
    if (response.contentLength != null && response.contentLength != size) {
      throw const FormatException('固件下载长度不符');
    }
    final builder = BytesBuilder(copy: false);
    var received = 0;
    await for (final chunk
        in response.stream.timeout(const Duration(seconds: 30))) {
      checkActive();
      received += chunk.length;
      if (received > size) throw const FormatException('固件下载超过声明长度');
      builder.add(chunk);
    }
    checkActive();
    final bytes = builder.takeBytes();
    if (bytes.length != size || sha256.convert(bytes).toString() != digest) {
      throw const FormatException('固件下载不完整或 SHA256 校验失败，请重试');
    }
    return DownloadedFirmware(bytes, version,
        ticket: ticket, expiresAt: grantedAt.add(const Duration(seconds: 300)));
  }
}
