import 'package:flutter/services.dart';

class ImeRelay {
  static const _channel = MethodChannel('pcflash/ime');

  static Future<int?> beginRemote() =>
      _channel.invokeMethod<int>('beginRemote');
  static Future<bool> permitsRemote(int token) async =>
      await _channel.invokeMethod<bool>('permitsRemote', {'token': token}) ==
      true;
  static Future<void> endRemote(int token) =>
      _channel.invokeMethod<void>('endRemote', {'token': token});
  static Future<void> cancelVoiceForStop() =>
      _channel.invokeMethod<void>('cancelVoiceForStop');
  static Future<bool> resumeRemote() async =>
      await _channel.invokeMethod<bool>('resumeRemote') == true;
  static Future<Map<String, dynamic>> status() async =>
      await _channel.invokeMapMethod<String, dynamic>('status') ?? {};

  static Future<Map<String, dynamic>> pasteText(String text, int token) async =>
      await _channel.invokeMapMethod<String, dynamic>('pasteText', {
        'text': text,
        'token': token,
        'enter': false,
        'timeoutMs': 8000,
      }).timeout(const Duration(seconds: 10)) ??
      {'ok': false, 'reason': 'paste_unknown'};
}
