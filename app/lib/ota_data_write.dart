import 'dart:async';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';

/// Only an explicit Android ATT resource rejection is safe to retry.
/// A timeout or disconnected write can have an unknown result and must stop.
Future<void> writeOtaData({
  required Future<void> Function() write,
  required void Function() checkActive,
  Future<void> Function(Duration)? wait,
}) async {
  final pause = wait ?? Future<void>.delayed;
  for (var retries = 0;; retries++) {
    checkActive();
    try {
      await write();
      checkActive();
      return;
    } on FlutterBluePlusException catch (error) {
      if (error.platform != ErrorPlatform.android ||
          error.function != 'writeCharacteristic' ||
          error.code != 17) {
        rethrow;
      }
      checkActive();
      if (retries >= 20) {
        throw StateError('控制板接收繁忙，本次更新已停止。请保持供电，重新连接蓝牙后再试（蓝牙错误17）。');
      }
      await pause(const Duration(milliseconds: 100));
    }
  }
}

Future<void> waitForOtaReceiver({
  required Future<List<int>> Function() read,
  required void Function() checkActive,
  Future<void> Function(Duration)? wait,
}) async {
  final pause = wait ?? Future<void>.delayed;
  for (var attempt = 0; attempt < 150; attempt++) {
    checkActive();
    final status = await read();
    checkActive();
    if (status.length < 3) throw StateError('控制板升级状态不完整，请重新连接后检查版本');
    if (status[0] == 1) return;
    if (status[0] == 4) throw StateError('控制板未能准备升级，请检查设备状态（错误码 ${status[2]}）');
    if (status[0] != 0) throw StateError('控制板不处于接收状态，请重新连接后检查版本');
    await pause(const Duration(milliseconds: 100));
  }
  throw StateError('控制板准备升级超时，本次更新已停止，请保持供电并重新连接');
}
