import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:pcflash/ble_ota_service.dart';
import 'package:pcflash/board_info.dart';
import 'package:pcflash/cloud_relay.dart';
import 'package:pcflash/control_client.dart';
import 'package:pcflash/diagnostics.dart';
import 'package:pcflash/relay_selfheal.dart';

class HealBoard extends BleOtaService {
  String nonce = '12' * 16, identity = 'test-board';
  int writes = 0, proofs = 0, disconnects = 0;
  @override
  bool get supportsLocalControl => true;
  @override
  Future<BoardInfo?> readInfo() async => BoardInfo(identity, 'ci', '', '', 2);
  @override
  Future<List<int>> signDownloadChallenge(List<int> bytes) async {
    proofs++;
    return List.filled(32, 187);
  }

  @override
  Future<Map<String, dynamic>> readLocalControl() async => {
        'nonce': nonce,
        'seq': 0,
        'op': 0,
        'result': 0,
        'busy': 0,
        'hid': 0,
        'ready': 1
      };
  @override
  Future<void> writeLocalControl(List<int> bytes) async {
    writes++;
  }

  @override
  Future<void> disconnect() async {
    disconnects++;
  }
}

Future<void> waitFor(bool Function() ready,
    {Duration limit = const Duration(seconds: 20)}) async {
  final watch = Stopwatch()..start();
  while (!ready() && watch.elapsed < limit) {
    await Future<void>.delayed(const Duration(milliseconds: 20));
  }
  expect(ready(), true, reason: 'condition not reached within $limit');
}

void main() {
  group('RelaySelfHeal policy', () {
    test('backoff is 1,2,4,8,16,30 capped and never zero after attempt 1', () {
      expect(RelaySelfHeal.maxAttempts, 8);
      expect(RelaySelfHeal.backoffSeconds, [1, 2, 4, 8, 16, 30, 30, 30]);
      expect(RelaySelfHeal.delayBefore(1), Duration.zero);
      expect(RelaySelfHeal.delayBefore(2), const Duration(seconds: 1));
      expect(RelaySelfHeal.delayBefore(3), const Duration(seconds: 2));
      expect(RelaySelfHeal.delayBefore(4), const Duration(seconds: 4));
      expect(RelaySelfHeal.delayBefore(5), const Duration(seconds: 8));
      expect(RelaySelfHeal.delayBefore(6), const Duration(seconds: 16));
      expect(RelaySelfHeal.delayBefore(7), const Duration(seconds: 30));
      expect(RelaySelfHeal.delayBefore(8), const Duration(seconds: 30));
      expect(RelaySelfHeal.delayBefore(9), const Duration(seconds: 30));
      final total = List.generate(RelaySelfHeal.maxAttempts, (i) => i + 1)
          .map(RelaySelfHeal.delayBefore)
          .fold(Duration.zero, (a, b) => a + b);
      expect(total, const Duration(seconds: 91)); // 0+1+2+4+8+16+30+30
    });

    test('only a relay capability denial counts as a permission error', () {
      expect(
          RelaySelfHeal.permissionError(
              ControlHttpFailure(403, 'relay expired', relayDenial: true)),
          true);
      expect(
          RelaySelfHeal.permissionError(
              ControlHttpFailure(401, 'ticket', relayDenial: true)),
          true);
      // Non-relay paths, detach denials and lease holds keep old meaning.
      expect(RelaySelfHeal.permissionError(ControlHttpFailure(403, 'denied')),
          false);
      expect(
          RelaySelfHeal.permissionError(
              ControlHttpFailure(409, 'lease', relayLeaseExpired: true)),
          false);
      expect(RelaySelfHeal.permissionError(const FormatException('bad')), false);
      expect(RelaySelfHeal.permissionError(StateError('identity')), false);
    });

    test('denial text names every server reason without leaking values', () {
      for (final text in [
        'gateway lease held',
        'relay expired; reconcile first',
        'ticket invalid',
        'expired'
      ]) {
        expect(RelaySelfHeal.denialText(text), true, reason: text);
      }
      expect(RelaySelfHeal.denialText('internal error'), false);
      expect(RelaySelfHeal.denialText(null), false);
      expect(RelaySelfHeal.reasonText(ControlHttpFailure(403, 'gateway lease')),
          '网关租约失效');
      expect(RelaySelfHeal.reasonText(ControlHttpFailure(403, 'nope')),
          isNot(contains('ticket')));
    });

    test('transient failures retry, identity/protocol failures do not', () {
      expect(RelaySelfHeal.retryable(ControlHttpFailure(503, 'busy')), true);
      expect(RelaySelfHeal.retryable(http.ClientException('lost')), true);
      expect(
          RelaySelfHeal.retryable(
              TimeoutException('slow', const Duration(seconds: 1))),
          true);
      expect(RelaySelfHeal.retryable(const SocketException('down')), false);
      expect(RelaySelfHeal.retryable(StateError('控制板身份已改变')), false);
      expect(RelaySelfHeal.retryable(const FormatException('授权挑战无效')),
          false);
    });
  });

  test('relay denial re-authorizes with a fresh ticket and resumes polling',
      () async {
    final board = HealBoard();
    final calls = <String>[];
    final tickets = <String>[];
    var authorizations = 0, attaches = 0, polls = 0;
    final client = ControlClient(
        healDelay: (_) => const Duration(milliseconds: 10),
        client: MockClient((request) async {
          final op = request.url.path.split('/').last;
          calls.add(op);
          final auth = request.headers['Authorization'];
          if (auth != null) tickets.add(auth);
          if (op == 'detach') return http.Response('{}', 403);
          if (op == 'authorize') {
            authorizations++;
            return http.Response(
                jsonEncode({
                  'ticket': 't' * 43,
                  'expiresIn': 300,
                  'scope': 'phone-commands'
                }),
                200);
          }
          if (op == 'attach') {
            attaches++;
            return http.Response(jsonEncode({'state': 'connected'}), 200);
          }
          if (op == 'poll') {
            polls++;
            if (attaches == 1) {
              return http.Response(
                  jsonEncode({'reply': 'relay expired; reconcile first'}), 403);
            }
            return http.Response(jsonEncode({'state': 'idle'}), 200);
          }
          if (op == 'challenge') {
            return http.Response(jsonEncode({'challenge': 'a' * 64}), 200);
          }
          return http.Response('{}', 404);
        }));
    await client.authorize(board);
    await waitFor(() => client.authorized && polls > 1);
    expect(authorizations, 2, reason: 'full challenge+authorize once, not renew');
    expect(attaches, 2);
    expect(calls.contains('renew'), false);
    expect(client.selfHealing, false);
    expect(client.selfHealExhausted, false);
    expect(client.connectionStatus, contains('云端动作需回执确认'));
    expect(board.writes, 0);
    await client.shutdown();
  });

  test('bounded attempts end in idle, not a busy retry loop', () async {
    final board = HealBoard();
    var authorizations = 0, polls = 0;
    final client = ControlClient(
        healDelay: (_) => const Duration(milliseconds: 5),
        client: MockClient((request) async {
          final op = request.url.path.split('/').last;
          if (op == 'detach') return http.Response('{}', 403);
          if (op == 'poll') {
            polls++;
            return http.Response(jsonEncode({'code': 'relay_lease_expired'}), 403);
          }
          if (op == 'authorize') {
            authorizations++;
            return http.Response(
                jsonEncode({
                  'ticket': 't' * 43,
                  'expiresIn': 300,
                  'scope': 'phone-commands'
                }),
                200);
          }
          if (op == 'challenge') {
            return http.Response(jsonEncode({'challenge': 'a' * 64}), 200);
          }
          if (op == 'attach') {
            return http.Response(jsonEncode({'state': 'connected'}), 200);
          }
          return http.Response('{}', 404);
        }));
    await client.authorize(board);
    await waitFor(() => client.selfHealExhausted);
    final settledPolls = polls;
    expect(authorizations, RelaySelfHeal.maxAttempts + 1);
    expect(client.authorized, false);
    expect(client.connectionStatus, contains('自动重连已停止'));
    expect(client.selfHealStatus, contains('自动重连已停止'));
    await Future<void>.delayed(const Duration(milliseconds: 400));
    expect(polls, settledPolls, reason: 'no polling after the budget is spent');
    expect(board.writes, 0);
    await client.shutdown();
  });

  test('ticket expiry while polling re-authorizes before the next denial',
      () async {
    final board = HealBoard();
    var authorizations = 0, attaches = 0, polls = 0;
    final client = ControlClient(
        healDelay: (_) => const Duration(milliseconds: 5),
        client: MockClient((request) async {
          final op = request.url.path.split('/').last;
          if (op == 'detach') return http.Response('{}', 403);
          if (op == 'poll') {
            polls++;
            return http.Response(jsonEncode({'state': 'idle'}), 200);
          }
          if (op == 'authorize') {
            authorizations++;
            return http.Response(
                jsonEncode({
                  'ticket': 't' * 43,
                  'expiresIn': authorizations == 1 ? 1 : 300,
                  'scope': 'phone-commands'
                }),
                200);
          }
          if (op == 'challenge') {
            return http.Response(jsonEncode({'challenge': 'a' * 64}), 200);
          }
          if (op == 'attach') {
            attaches++;
            return http.Response(jsonEncode({'state': 'connected'}), 200);
          }
          return http.Response('{}', 404);
        }));
    await client.authorize(board);
    await waitFor(() => authorizations >= 2);
    expect(attaches, 2);
    expect(polls, greaterThan(0));
    await client.shutdown();
  });

  test('non-capability relay failure never re-authorizes', () async {
    final board = HealBoard();
    var authorizations = 0;
    final client = ControlClient(
        healDelay: (_) => const Duration(milliseconds: 5),
        client: MockClient((request) async {
          final op = request.url.path.split('/').last;
          if (op == 'detach') return http.Response('{}', 403);
          if (op == 'poll') return http.Response('{}', 500);
          if (op == 'authorize') {
            authorizations++;
            return http.Response(
                jsonEncode({
                  'ticket': 't' * 43,
                  'expiresIn': 300,
                  'scope': 'phone-commands'
                }),
                200);
          }
          if (op == 'challenge') {
            return http.Response(jsonEncode({'challenge': 'a' * 64}), 200);
          }
          if (op == 'attach') {
            return http.Response(jsonEncode({'state': 'connected'}), 200);
          }
          return http.Response('{}', 404);
        }));
    await client.authorize(board);
    await waitFor(() => !client.authorized && client.selfHealStatus == null);
    await Future<void>.delayed(const Duration(milliseconds: 300));
    expect(authorizations, 1);
    expect(client.selfHealExhausted, false);
    await client.shutdown();
  });

  test('CloudRelay without a denial keeps its old single-stop behaviour',
      () async {
    var disconnects = 0;
    final events = <String>[];
    final relay = CloudRelay(
      post: (op, body) async {
        events.add(op);
        if (op == 'attach') return {'state': 'connected'};
        if (op == 'poll') throw ControlHttpFailure(403, 'denied');
        return {'state': 'idle'};
      },
      read: () async => {'nonce': '12' * 16},
      write: (_) async {},
      disconnect: () async => disconnects++,
      onError: (_) {},
    );
    await relay.start();
    await Future<void>.delayed(const Duration(milliseconds: 1200));
    expect(relay.isClosed, true);
    expect(disconnects, 1);
    await relay.close();
  });
}
