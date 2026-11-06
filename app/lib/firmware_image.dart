import 'dart:typed_data';
import 'package:crypto/crypto.dart';

/// Validates the same S3 app image contract as the private cloud publisher.
class FirmwareImage {
  final String version;
  final String sha;
  final String elfSha256;
  final String project;
  const FirmwareImage(this.version, this.sha, this.elfSha256,
      {this.project = 'phone_controller_epaper'});
  static const maxSize = 0x340000;

  /// Reject unknown or same-day ordering until a signed release sequence exists.
  void assertUpgradeAllowed(String currentVersion, {bool confirmed = false}) {
    if (project == 'phone_controller_amoled') {
      List<int> parts(String value) {
        final m = RegExp(
                r'^(0|[1-9][0-9]{0,4})\.(0|[1-9][0-9]{0,4})\.(0|[1-9][0-9]{0,4})-amoled$')
            .firstMatch(value);
        if (m == null) throw StateError('无法比较AMOLED固件版本，已停止更新');
        return [int.parse(m[1]!), int.parse(m[2]!), int.parse(m[3]!)];
      }

      final target = parts(version), current = parts(currentVersion);
      if (confirmed) return;
      for (var i = 0; i < 3; i++) {
        if (target[i] > current[i]) return;
        if (target[i] < current[i]) break;
      }
      throw StateError('目标固件不是可确认的较新版本，已停止更新');
    }
    DateTime day(String value) {
      final match = RegExp(r'^(\d{4})\.(\d{2})\.(\d{2})-[a-zA-Z0-9._-]+$')
          .firstMatch(value);
      if (match == null) throw StateError('无法比较固件版本，已停止更新');
      final year = int.parse(match[1]!);
      final month = int.parse(match[2]!);
      final day = int.parse(match[3]!);
      final result = DateTime.utc(year, month, day);
      if (result.year != year || result.month != month || result.day != day) {
        throw StateError('固件版本日期无效，已停止更新');
      }
      return result;
    }

    final targetDay = day(version), currentDay = day(currentVersion);
    if (confirmed) return;
    if (!targetDay.isAfter(currentDay)) {
      throw StateError('目标固件不是可确认的较新版本，已停止更新');
    }
  }

  static FirmwareImage parse(Uint8List bytes, {String? boardModel}) {
    if (boardModel != null && boardModel != 'esp32-s3-touch-amoled-2.16') {
      throw const FormatException('未知控制板型号，已停止更新');
    }
    final project = boardModel == 'esp32-s3-touch-amoled-2.16'
        ? 'phone_controller_amoled'
        : 'phone_controller_epaper';
    final limit = project == 'phone_controller_amoled' ? 0x600000 : maxSize;
    void reject(String message) => throw FormatException(message);
    if (bytes.length < 4096 || bytes.length > limit) {
      reject('固件大小无效，必须是槽位范围内的 app.bin');
    }
    final data = ByteData.sublistView(bytes);
    if (bytes[0] != 0xe9 ||
        bytes[1] < 1 ||
        bytes[1] > 16 ||
        data.getUint16(12, Endian.little) != 9) {
      reject('固件不是 ESP32-S3 应用镜像');
    }
    if (data.getUint32(28, Endian.little) < 256 ||
        data.getUint32(32, Endian.little) != 0xabcd5432) {
      reject('固件缺少有效应用描述');
    }
    String field(int offset) {
      final raw = bytes.sublist(offset, offset + 32);
      final end = raw.indexOf(0);
      if (end <= 0) reject('固件版本或项目字段无效');
      final value = String.fromCharCodes(raw.sublist(0, end));
      if (!RegExp(r'^[a-zA-Z0-9._-]{1,31}$').hasMatch(value)) {
        reject('固件版本或项目字段无效');
      }
      return value;
    }

    final version = field(48);
    if (field(80) != project) reject('固件与控制板项目不匹配');
    var offset = 24;
    var checksum = 0xef;
    for (var i = 0; i < bytes[1]; i++) {
      if (offset + 8 > bytes.length) reject('固件段头不完整');
      final size = data.getUint32(offset + 4, Endian.little);
      offset += 8;
      if (size > bytes.length - offset) reject('固件段数据不完整');
      for (var n = offset; n < offset + size; n++) {
        checksum ^= bytes[n];
      }
      offset += size;
    }
    final end = (offset ~/ 16 + 1) * 16;
    if (end > bytes.length || bytes[end - 1] != checksum) {
      reject('固件镜像校验失败');
    }
    if (bytes[23] != 1 || bytes.length != end + 32) {
      reject('固件缺少完整 SHA256 校验');
    }
    final digest = sha256.convert(Uint8List.sublistView(bytes, 0, end)).bytes;
    for (var i = 0; i < 32; i++) {
      if (bytes[end + i] != digest[i]) reject('固件 SHA256 校验失败');
    }
    return FirmwareImage(
        version,
        sha256.convert(bytes).toString(),
        bytes
            .sublist(176, 208)
            .map((b) => b.toRadixString(16).padLeft(2, '0'))
            .join(),
        project: project);
  }
}
