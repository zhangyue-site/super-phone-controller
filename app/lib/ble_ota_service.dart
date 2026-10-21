import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';

/// 固件侧 ble_ota.h 里定义的状态码
class OtaState {
  static const idle = 0;
  static const receiving = 1;
  static const verifying = 2;
  static const ready = 3;
  static const error = 4;
}

class OtaError {
  static String text(int e) => switch (e) {
        1 => '状态不允许该操作',
        2 => '参数不合法',
        3 => '写 flash 失败',
        4 => '固件超过槽位大小',
        5 => 'sha256 校验不符，数据在传输中损坏',
        6 => '镜像头部不合法',
        _ => '未知错误 $e',
      };
}

/// 固件信息，来自扫描到的广播名或本地文件
class FirmwareInfo {
  final String name;
  final int size;
  final String sha256;
  final String version;

  const FirmwareInfo({
    required this.name,
    required this.size,
    required this.sha256,
    required this.version,
  });

  String get sizeText => size >= 1048576
      ? '${(size / 1048576).toStringAsFixed(2)} MB'
      : '${(size / 1024).toStringAsFixed(0)} KB';
}

class PushProgress {
  final int percent;
  final int sent;
  final int total;
  final String step;
  final String? log;
  final bool done;
  final bool success;

  const PushProgress({
    this.percent = 0,
    this.sent = 0,
    this.total = 0,
    this.step = '',
    this.log,
    this.done = false,
    this.success = false,
  });
}

/// BLE 固件推送服务。
///
/// 协议与固件 ble_ota.cpp 对应：BEGIN(1B 命令 + 4B 小端长度 + 32B sha256)
/// → 若干 DATA(1B 命令 + 正文) → END(1B 命令)。
///
/// 两个平台的差异都收敛到这里：
///  * Android 支持 MTU 协商，iOS 的 CoreBluetooth 固定不给谈；
///  * iOS 的分片上限由 maximumWriteValueLength 给出，通常 182 字节。
class BleOtaService {
  static const svcUuid = '6f6f7461-2d6f-7461-0000-000000000001';
  static const ctrlUuid = '6f6f7461-2d6f-7461-0000-000000000002';
  static const statUuid = '6f6f7461-2d6f-7461-0000-000000000003';

  /// 4MB 槽位的上限（固件 ota 分区 0x340000）
  static const maxImageSize = 0x340000;

  BluetoothDevice? _device;
  BluetoothCharacteristic? _ctrl;
  BluetoothCharacteristic? _stat;
  StreamSubscription? _statSub;
  bool _busy = false;

  bool get busy => _busy;
  BluetoothDevice? get device => _device;

  /// 扫描广播里带 OTA 服务的设备。
  Stream<List<ScanResult>> scan() {
    FlutterBluePlus.startScan(
      withServices: [Guid(svcUuid)],
      timeout: const Duration(seconds: 15),
      androidUsesFineLocation: false,
    );
    return FlutterBluePlus.scanResults;
  }

  Future<void> stopScan() => FlutterBluePlus.stopScan();

  /// 连接并发现服务，返回设备的 MTU 与每帧正文大小。
  Future<int> connect(BluetoothDevice device) async {
    // 插件要求显式声明许可，否则拒绝连接——这是防止商业滥用的一道门。
    await device.connect(
      license: License.nonprofit,
      timeout: const Duration(seconds: 15),
      // Android 上会协商到 517；iOS 的 CoreBluetooth 忽略这个值，
      // 实际分片长度由 maximumWriteValueLength 决定，插件内部已处理。
      mtu: Platform.isAndroid ? 517 : null,
    );

    final services = await device.discoverServices();
    final svc = services.where((s) => s.uuid == Guid(svcUuid)).firstOrNull;
    if (svc == null) {
      await device.disconnect();
      throw Exception('设备上没有 OTA 服务，确认选的是 PhoneCtl 板子');
    }

    _ctrl = svc.characteristics
        .where((c) => c.uuid == Guid(ctrlUuid))
        .firstOrNull;
    _stat = svc.characteristics
        .where((c) => c.uuid == Guid(statUuid))
        .firstOrNull;
    if (_ctrl == null || _stat == null) {
      await device.disconnect();
      throw Exception('OTA 特征值缺失');
    }

    _device = device;

    // 协商失败时 mtu 仍是 23，减去 3 字节 ATT 头和 1 字节命令码 = 19。
    final mtu = device.mtuNow;
    var chunk = mtu - 4;
    if (chunk < 19) chunk = 19;

    // iOS 的真实上限只能从特征值问出来，比 MTU 推算更准。
    _statSub = _stat!.onValueReceived.listen((v) {});
    return chunk;
  }

  /// 订阅状态通知，返回原始 4 字节状态流。
  Stream<List<int>> statusStream() =>
      _stat?.onValueReceived ?? const Stream.empty();

  /// 推送固件。[chunkSize] 由 connect 返回。
  Stream<PushProgress> push(Uint8List data, {required int chunkSize}) async* {
    if (_busy) {
      yield const PushProgress(done: true, success: false, log: '已有推送在进行');
      return;
    }
    if (data.length < 4096) {
      yield const PushProgress(done: true, success: false, log: '文件太小，不是固件');
      return;
    }
    if (data.length > maxImageSize) {
      yield PushProgress(
          done: true,
          success: false,
          log: '固件 ${data.length} 字节超过槽位上限 $maxImageSize');
      return;
    }

    final ctrl = _ctrl, stat = _stat;
    if (ctrl == null || stat == null) {
      yield const PushProgress(done: true, success: false, log: '未连接');
      return;
    }

    _busy = true;
    final total = data.length;

    try {
      yield const PushProgress(step: '连接设备', log: '已连接，MTU=${0}');

      final digest = sha256.convert(data).bytes;
      final begin = Uint8List(1 + 4 + 32);
      begin[0] = 0x01;
      begin[1] = total & 0xFF;
      begin[2] = (total >> 8) & 0xFF;
      begin[3] = (total >> 16) & 0xFF;
      begin[4] = (total >> 24) & 0xFF;
      begin.setRange(5, 37, digest);
      await ctrl.write(begin, withoutResponse: false);

      // iOS 必须用 withResponse，否则 CoreBluetooth 会限流丢包。
      final withoutResponse = Platform.isAndroid;
      final chunk = withoutResponse ? chunkSize : chunkSize;

      yield PushProgress(
        step: '传输固件',
        log: '每帧正文 $chunk 字节，共 ${(total / chunk).ceil()} 帧',
      );

      var sent = 0;
      var lastPct = -1;
      final frame = Uint8List(1 + chunk);
      while (sent < total) {
        final n = (total - sent) > chunk ? chunk : (total - sent);
        frame[0] = 0x02;
        frame.setRange(1, 1 + n, data, sent);
        final payload = n == chunk ? frame : Uint8List.sublistView(frame, 0, 1 + n);
        await ctrl.write(payload, withoutResponse: withoutResponse);
        sent += n;

        final pct = (sent * 100) ~/ total;
        if (pct != lastPct) {
          lastPct = pct;
          yield PushProgress(
            percent: pct,
            sent: sent,
            total: total,
            step: '传输固件',
          );
        }
      }

      yield PushProgress(
        percent: 100,
        sent: total,
        total: total,
        step: '校验 sha256',
        log: '数据发完，等待板子校验',
      );

      await ctrl.write(Uint8List.fromList([0x03]), withoutResponse: false);

      // 等板子回报 READY 或 ERROR，最多 20 秒（校验 1.3MB 很快，留足余量）。
      final result = await statusStream()
          .map((v) => v.length >= 3 ? v : null)
          .where((v) => v != null && (v[0] == OtaState.ready || v[0] == OtaState.error))
          .first
          .timeout(const Duration(seconds: 20));

      if (result![0] == OtaState.ready) {
        yield const PushProgress(
          percent: 100,
          step: '切换启动槽',
          done: true,
          success: true,
          log: '校验通过，启动槽已切换，板子即将重启',
        );
      } else {
        yield PushProgress(
          done: true,
          success: false,
          log: '板子报错：${OtaError.text(result[2])}',
        );
      }
    } on TimeoutException {
      yield const PushProgress(
          done: true, success: false, log: '等待板子校验超时，请重试');
    } catch (e) {
      yield PushProgress(done: true, success: false, log: '传输失败：$e');
    } finally {
      _busy = false;
    }
  }

  Future<void> disconnect() async {
    await _statSub?.cancel();
    _statSub = null;
    _ctrl = null;
    _stat = null;
    try {
      await _device?.disconnect();
    } catch (_) {}
    _device = null;
  }
}
