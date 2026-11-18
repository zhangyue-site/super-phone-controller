import 'package:flutter/services.dart';

/// Dart 侧桥：paste_text(op=15) 由 CloudRelay 调这里。
class ImeRelay {
  static const _channel = MethodChannel('pcflash/ime');

  static Future<Map<String, dynamic>> status() async =>
      await _channel.invokeMapMethod<String, dynamic>('status') ?? {};

  /// 返回 {ok: bool, reason: String}；
  /// reason∈''|ime_not_authorized|paste_timeout|ime_switch_failed|paste_failed
  static Future<Map<String, dynamic>> pasteText(String text,
      {bool enter = false,
      Duration timeout = const Duration(seconds: 8)}) async {
    try {
      final r = await _channel.invokeMapMethod<String, dynamic>('pasteText', {
        'text': text,
        'enter': enter,
        'timeoutMs': timeout.inMilliseconds,
      }).timeout(timeout + const Duration(seconds: 2));
      return r ?? {'ok': false, 'reason': 'paste_failed'};
    } on PlatformException catch (e) {
      return {'ok': false, 'reason': e.code};
    }
  }
}
