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
      int? remainingMs,
      int? attempt,
      int? stageMs,
      bool? writeStarted,
      String? failureKind,
      String? errorType}) {
    final type =
        errorType ?? (error == null ? 'None' : error.runtimeType.toString());
    final kind = const {
      'TimeoutException',
      'StateError',
      'FormatException',
      'ControlHttpFailure',
      'PlatformException',
      'ClientException'
    }.contains(type)
        ? type
        : type == 'None'
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
        if (attempt != null) 'attempt': attempt,
        if (stageMs != null) 'stage_ms': stageMs,
        if (writeStarted != null) 'write_started': writeStarted,
        if (const {
          'maintenance_unconfirmed',
          'ota_unconfirmed',
          'input_outcome_unknown',
          'input_not_dispatched',
          'control_unconfirmed',
          'transport_unconfirmed'
        }.contains(failureKind))
          'failure_kind': failureKind,
      }).catchError((_) {}));
    } catch (_) {/* Pure tests or a detached engine have no messenger. */}
  }

  static Future<String> read() async =>
      await channel.invokeMethod<String>('diagnostics') ?? '[]';
}

class ControlHttpFailure extends FormatException {
  final int status;
  final bool relayLeaseExpired;

  /// Set only when a relay data path (attach/poll/ack/maintenance) was denied
  /// for a capability reason. Such a denial is recoverable by re-authorizing
  /// in place; every other 403 keeps its previous terminal meaning.
  final bool relayDenial;
  ControlHttpFailure(this.status, String message,
      {this.relayLeaseExpired = false, this.relayDenial = false})
      : super(message);
}
