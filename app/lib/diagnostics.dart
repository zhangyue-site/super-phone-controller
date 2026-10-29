import 'dart:async';
import 'package:flutter/services.dart';

/// No messages, URLs, tickets, nonces, packets or response bodies enter this API.
class SafeDiagnostics {
  static const channel = MethodChannel('pcflash/app');
  static void record(String event,
      {String phase = 'unknown',
      String reason = 'none',
      Object? error,
      int? httpStatus,
      int? op,
      int? seq,
      int? lastOp,
      int? lastSeq,
      int? remainingMs}) {
    final type = error == null ? 'None' : error.runtimeType.toString();
    final kind = const {
      'TimeoutException',
      'StateError',
      'FormatException',
      'ControlHttpFailure',
      'PlatformException',
      'ClientException'
    }.contains(type)
        ? type
        : error == null
            ? 'None'
            : 'Unknown';
    try {
      unawaited(channel.invokeMethod<void>('diagnosticEvent', {
        'event': event,
        'phase': phase,
        'reason': reason,
        'error_type': kind,
        if (httpStatus != null) 'http_status': httpStatus,
        if (op != null) 'op': op,
        if (seq != null) 'seq': seq,
        if (lastOp != null) 'last_op': lastOp,
        if (lastSeq != null) 'last_seq': lastSeq,
        if (remainingMs != null) 'remaining_ms': remainingMs,
      }).catchError((_) {}));
    } catch (_) {/* Pure tests or a detached engine have no messenger. */}
  }

  static Future<String> read() async =>
      await channel.invokeMethod<String>('diagnostics') ?? '[]';
}

class ControlHttpFailure extends FormatException {
  final int status;
  ControlHttpFailure(this.status, String message) : super(message);
}
