import 'dart:async';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/cloud_relay.dart';

const channel = MethodChannel('pcflash/ime');
const nonce = '0123456789abcdef0123456789abcdef';

Map<String, dynamic> packet(int op, int seq) => {
      'state': 'action',
      'packet': '00' * 48,
      'id': 'cmd-$seq',
      'seq': seq,
      'op': op,
      if (op == 11 || op == 12) 'expiresIn': 15,
    };
Map<String, dynamic> textAction() => {
      'state': 'action_text',
      'op': 15,
      'id': 'draft-one',
      'seq': 1,
      'text': '测试'
    };

class Transport {
  final List<Map<String, dynamic>> pending;
  Transport(this.pending);
  final events = <String>[];
  final acks = <Map<String, dynamic>>[];
  final ended = Completer<Object>();
  final exhausted = Completer<void>();
  bool loseTextAck = false;
  var current = <String, dynamic>{};
  late final relay = CloudRelay(
    guardAndroidInput: true,
    post: (path, body) async {
      events.add(path);
      if (path == 'poll') {
        if (pending.isEmpty) {
          if (!exhausted.isCompleted) exhausted.complete();
          return {'state': 'idle'};
        }
        current = pending.removeAt(0);
        return current;
      }
      if (path == 'ack-text') {
        acks.add(body);
        if (loseTextAck) throw TimeoutException('lost ACK');
        return {'state': body['ok'] == true ? 'acknowledged' : 'failed'};
      }
      return {'state': 'acknowledged'};
    },
    write: (_) async {
      events.add('write:${current['op']}');
    },
    read: () async => {
      'nonce': nonce,
      'op': current['op'] ?? 0,
      'seq': current['seq'] ?? 0,
      'busy': 0,
      'ready': 1,
      'hid': 0,
      'result': current['op'] == 5 ? 5 : 3
    },
    disconnect: () async {
      events.add('disconnected');
    },
    onError: (error) {
      if (!ended.isCompleted) ended.complete(error);
    },
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  tearDown(() => messenger.setMockMethodCallHandler(channel, null));
  test(
      'maintenance, idle and repeated STOP never adopt the keyboard or duplicate STOP',
      () async {
    final t = Transport([
      packet(12, 1),
      packet(5, 2),
      packet(5, 2),
      {...packet(5, 2), 'id': 'new-task-stop'},
      packet(12, 3)
    ]);
    final calls = <String>[];
    messenger.setMockMethodCallHandler(channel, (m) async {
      calls.add(m.method);
      return null;
    });
    await t.relay.start();
    await t.exhausted.future.timeout(const Duration(seconds: 5));
    await t.relay.close();
    expect(t.events.where((e) => e.startsWith('write:')),
        ['write:12', 'write:5', 'write:5', 'write:12']);
    expect(calls, ['cancelVoiceForStop', 'cancelVoiceForStop']);
    expect(t.relay.taskStopAcknowledged, true);
  });
  test('held HID command detaches and never executes after a later resume',
      () async {
    final t = Transport([packet(3, 1)]);
    final calls = <String>[];
    messenger.setMockMethodCallHandler(channel, (m) async {
      calls.add(m.method);
      return null;
    });
    await t.relay.start();
    await t.ended.future.timeout(const Duration(seconds: 3));
    expect(t.events, containsAllInOrder(['poll', 'disconnected', 'detach']));
    expect(t.events.any((e) => e.startsWith('write:')), false);
    expect(t.relay.recoverableNetworkFailure, false);
    expect(calls, ['beginRemote']);
  });
  test(
      'takeover between lease and USB dispatch rejects the write and ends the exact lease',
      () async {
    final t = Transport([packet(6, 1)]);
    final calls = <String>[];
    messenger.setMockMethodCallHandler(channel, (m) async {
      calls.add(m.method);
      if (m.method == 'beginRemote') return 7;
      expect(m.arguments['token'], 7);
      return m.method == 'permitsRemote' ? false : null;
    });
    await t.relay.start();
    await t.ended.future.timeout(const Duration(seconds: 3));
    expect(t.events.contains('write:6'), false);
    expect(calls, ['beginRemote', 'permitsRemote', 'endRemote']);
  });
  test(
      'manual refusal of op15 sends one cloud-compatible negative ack without pasting',
      () async {
    final t = Transport([textAction(), textAction()]);
    final calls = <String>[];
    messenger.setMockMethodCallHandler(channel, (m) async {
      calls.add(m.method);
      return null;
    });
    await t.relay.start();
    await t.ended.future.timeout(const Duration(seconds: 4));
    expect(calls, ['beginRemote']);
    expect(t.events.where((e) => e == 'poll').length, 1);
    expect(
        t.events, containsAllInOrder(['ack-text', 'disconnected', 'detach']));
    expect(t.acks, [
      {'nonce': nonce, 'id': 'draft-one', 'ok': false, 'reason': 'paste_failed'}
    ]);
    expect(t.relay.recoverableNetworkFailure, false);
  });
  test(
      'native commit precedes text acknowledgment; loss never retries the text',
      () async {
    final t = Transport([textAction(), textAction()])..loseTextAck = true;
    final started = Completer<void>(), finish = Completer<void>();
    messenger.setMockMethodCallHandler(channel, (m) async {
      t.events.add(m.method);
      if (m.method == 'beginRemote') return 25;
      expect(m.arguments['token'], 25);
      if (m.method == 'pasteText') {
        expect(m.arguments['enter'], false);
        started.complete();
        await finish.future;
        return {'ok': true, 'reason': ''};
      }
      return null;
    });
    await t.relay.start();
    await started.future.timeout(const Duration(seconds: 3));
    expect(t.acks, isEmpty);
    finish.complete();
    await t.ended.future.timeout(const Duration(seconds: 3));
    expect(
        t.events,
        containsAllInOrder([
          'beginRemote',
          'pasteText',
          'ack-text',
          'endRemote',
          'disconnected',
          'detach'
        ]));
    expect(t.events.where((e) => e == 'pasteText').length, 1);
    expect(t.acks.single['ok'], true);
    expect(t.relay.recoverableNetworkFailure, false);
  });
}
