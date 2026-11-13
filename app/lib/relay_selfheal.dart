import 'dart:async';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'diagnostics.dart';
import 'gateway_recovery.dart';

/// Bounded, in-place relay re-authorization (vc60).
///
/// The server persists relay sessions and, once the board proves possession
/// again, adopts the session in place (TURN_ADOPT_AUTH). Reusing the same
/// physical session is therefore enough; only the capability has to be
/// re-issued. This file decides *when* a retry is allowed and *how far* it may
/// go. The handshake itself stays in ControlClient (challenge -> authorize ->
/// attach) and no protocol field, signature check or permission is changed.
class RelaySelfHeal {
  /// Hard ceiling: a full reconnect is attempted at most this many times in
  /// one incident, then the relay stays idle until a human reconnects.
  static const int maxAttempts = 8;

  /// 1s, 2s, 4s, 8s, 16s, 30s and then 30s capped. Never a busy loop.
  static const List<int> backoffSeconds = [1, 2, 4, 8, 16, 30, 30, 30];

  /// Delay before 1-based [attempt]: 1s,2s,4s,8s,16s,30s,30s,30s. Never zero,
  /// because every attempt re-runs a full handshake against the server.
  static Duration delayBefore(int attempt) {
    if (attempt <= 1) return Duration.zero;
    final index = (attempt - 2).clamp(0, backoffSeconds.length - 1);
    return Duration(seconds: backoffSeconds[index]);
  }

  static const _denialReasons = [
    'gateway lease',
    'relay expired',
    'reconcile',
    'expired',
    'ticket'
  ];

  /// Server-supplied denial text (reply/code) that means "prove yourself
  /// again", not "your board is the wrong board".
  static bool denialText(String? text) {
    if (text == null) return false;
    final value = text.toLowerCase();
    return _denialReasons.any(value.contains);
  }

  /// Only a relay data-path denial may re-authorize. A detach denial,
  /// a lease hold (409, owned by the existing STOP/detach recovery) and a
  /// non-relay 403 stay terminal exactly as before.
  static bool permissionError(Object error) =>
      error is ControlHttpFailure &&
      error.relayDenial &&
      !error.relayLeaseExpired;

  /// Transient failures are retried inside the attempt budget; identity,
  /// protocol and validation failures stop immediately (no guessing).
  static bool retryable(Object error) {
    if (error is ControlHttpFailure) return true;
    if (error is http.ClientException) return true;
    if (error is TimeoutException) return true;
    if (error is PlatformException) return true;
    if (error is BleReconnectFailure) return true;
    return false;
  }

  /// Short, ticket-free UI reason. Never echoes a ticket, nonce or body.
  static String reasonText(Object error) {
    if (error is ControlHttpFailure) {
      if (error.relayLeaseExpired) return '中继租约过期';
      final text = error.message.toLowerCase();
      if (text.contains('gateway lease')) return '网关租约失效';
      if (text.contains('relay expired') || text.contains('reconcile')) {
        return '中继会话已过期';
      }
      if (text.contains('ticket')) return '控制票据失效';
      if (text.contains('expired')) return '控制票据已过期';
      if (error.status == 401 || error.status == 403) {
        return '中继授权被拒（HTTP ${error.status}）';
      }
      return '中继请求失败（HTTP ${error.status}）';
    }
    if (error is TimeoutException) return '重新授权超时';
    if (error is http.ClientException) return '网络中断';
    if (error is StateError) return '控制板身份已改变';
    if (error is FormatException) return '授权响应无效';
    return '未知错误';
  }
}
