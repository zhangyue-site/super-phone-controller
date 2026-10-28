import 'dart:async';
import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:pcflash/control_client.dart';
import 'package:pcflash/ble_ota_service.dart';
import 'package:pcflash/board_info.dart';

const code = 'abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG';
Map<String, dynamic> grant({String scope = 'phone-commands'}) => {
      'ticket': 't' * 43,
      'device': 'test-board',
      'scope': scope,
      'expiresIn': 300,
    };

class TrackedTransport extends MockClient {
  TrackedTransport(super.fn);
  int closes = 0;
  @override
  void close() {
    closes++;
    super.close();
  }
}

class RenewalBoard extends BleOtaService {
  int identityReads = 0, signatures = 0, writes = 0;
  final disconnected = Completer<void>();
  @override
  bool get supportsLocalControl => true;
  @override
  Future<BoardInfo?> readInfo() async {
    identityReads++;
    return const BoardInfo('test-board', 'ci67', '', '', 2);
  }

  @override
  Future<List<int>> signDownloadChallenge(List<int> nonce) async {
    signatures++;
    return List.filled(32, 187);
  }

  @override
  Future<Map<String, dynamic>> readLocalControl() async => {
        'nonce': '12' * 16,
        'seq': writes,
        'op': writes == 0 ? 0 : 5,
        'result': writes == 0 ? 0 : 5,
        'busy': 0,
        'hid': 0,
        'ready': 1,
      };
  @override
  Future<void> writeLocalControl(List<int> bytes) async {
    writes++;
  }

  @override
  Future<void> disconnect() async {
    if (!disconnected.isCompleted) disconnected.complete();
  }
}

void main() {
  test('pair grants command-only capability and sends bearer for commands',
      () async {
    final paths = <String>[];
    final transport = TrackedTransport((request) async {
      paths.add(request.url.path.split('/').last);
      if (paths.last == 'pair-redeem') {
        expect(jsonDecode(request.body), {'code': code});
        expect(request.headers.containsKey('Authorization'), isFalse);
        return http.Response(jsonEncode(grant()), 200);
      }
      expect(paths.last, 'command');
      expect(request.headers['Authorization'], 'Bearer ${'t' * 43}');
      expect(
          jsonDecode(request.body), {'operation': 'prepare', 'text': '打开设置'});
      return http.Response('{"state":"pending"}', 200);
    });
    final client = ControlClient(client: transport);
    addTearDown(client.shutdown);
    await client.pair(code);
    expect(client.isPaired, isTrue);
    expect(client.deviceId, 'test-board');
    expect(client.authorized, isTrue);
    expect(client.canReadStatus, isTrue);
    expect((await client.command('prepare', text: '打开设置'))['state'], 'pending');
    await expectLater(client.pairingCode(), throwsStateError);
    await expectLater(client.revokeControllers(), throwsStateError);
    expect(paths, ['pair-redeem', 'command']);
    await client.shutdown();
    await client.shutdown();
    expect(transport.closes, 1);
    expect(client.authorized, isFalse);
    await expectLater(client.command('status'), throwsFormatException);
    expect(paths, ['pair-redeem', 'command']);
  });
  test('wrong scope is rejected without usable capability', () async {
    var requests = 0;
    final client = ControlClient(client: MockClient((_) async {
      requests++;
      return http.Response(jsonEncode(grant(scope: 'screen-upload')), 200);
    }));
    addTearDown(client.shutdown);
    await expectLater(client.pair(code), throwsFormatException);
    expect(client.isPaired, isFalse);
    expect(client.authorized, isFalse);
    await expectLater(
        client.command('prepare', text: '任务'), throwsFormatException);
    expect(requests, 1);
  });
  test('invalid code never opens network request', () async {
    var requests = 0;
    final client = ControlClient(client: MockClient((_) async {
      requests++;
      return http.Response('{}', 200);
    }));
    addTearDown(client.shutdown);
    for (final invalid in ['', 'a' * 42, 'a' * 44, '${'a' * 42}!', ' $code ']) {
      await expectLater(client.pair(invalid), throwsFormatException);
    }
    expect(requests, 0);
  });
  test('403 revokes paired grant and refresh never restores authority',
      () async {
    final paths = <String>[];
    final client = ControlClient(client: MockClient((request) async {
      paths.add(request.url.path.split('/').last);
      return paths.last == 'pair-redeem'
          ? http.Response(jsonEncode(grant()), 200)
          : http.Response('{"reply":"expired"}', 403);
    }));
    addTearDown(client.shutdown);
    await client.pair(code);
    await expectLater(client.command('status'), throwsFormatException);
    expect(client.authorized, isFalse);
    expect(client.canReadStatus, isFalse);
    await client.refresh();
    await expectLater(client.command('stop'), throwsFormatException);
    expect(paths, ['pair-redeem', 'command']);
  });
  test(
      'fresh unauthorized client refresh does not attempt renewal or BLE fallback',
      () async {
    var requests = 0;
    final client = ControlClient(client: MockClient((_) async {
      requests++;
      return http.Response('{}', 200);
    }));
    await client.refresh();
    await client.shutdown();
    await client.refresh();
    expect(requests, 0);
  });
  test('closed target relay cannot renew through BLE proof fallback', () async {
    final board = RenewalBoard();
    final paths = <String>[];
    final client = ControlClient(client: MockClient((request) async {
      final path = request.url.path.split('/').last;
      paths.add(path);
      final result = switch (path) {
        'challenge' => {'challenge': 'a' * 64},
        'authorize' => grant(),
        'attach' => {'state': 'connected'},
        'poll' => {
            'state': 'action',
            'id': 'stop',
            'seq': 1,
            'op': 5,
            'packet': '00' * 48
          },
        'ack' => {'state': 'acknowledged'},
        _ => {'state': 'stopped'},
      };
      return http.Response(jsonEncode(result), 200);
    }));
    addTearDown(client.shutdown);
    await client.authorize(board);
    await board.disconnected.future.timeout(const Duration(seconds: 3));
    expect(client.authorized, isFalse);
    final proofs = board.signatures, reads = board.identityReads;
    await client.refresh();
    expect(board.signatures, proofs);
    expect(board.identityReads, reads);
    expect(paths.where((p) => p == 'challenge').length, 1);
    expect(paths, isNot(contains('renew')));
  });
}
