import 'dart:convert';
import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/board_rpc.dart';

void main() {
  test(
      'BLE fragments correlate UTF8 request and multi-frame result without HTTP',
      () async {
    final output = <List<int>>[];
    final input = <int>[];
    final replies = <List<int>>[];
    final rpc = BoardRpc(
        mtu: 40,
        write: (bytes) async {
          final f = RpcFrame.decode(bytes);
          output.add(bytes);
          input.addAll(f.payload);
          if (input.length == f.total) {
            expect(
                (jsonDecode(utf8.decode(input)) as Map)['text'], '打开设置查看关于手机');
            final body = utf8.encode(jsonEncode({
              'status': 200,
              'body': {'state': 'pending', 'reply': '计划：打开设置查看关于手机'}
            }));
            for (var i = 0; i < body.length; i += 20) {
              final end = (i + 20).clamp(0, body.length);
              replies.add(
                  RpcFrame(2, f.id, i, body.length, body.sublist(i, end))
                      .encode());
            }
          }
        },
        read: () async {
          if (replies.isEmpty) throw StateError('pending');
          return replies.removeAt(0);
        });
    final result =
        await rpc.request({'operation': 'prepare', 'text': '打开设置查看关于手机'});
    expect(result['state'], 'pending');
    expect(output.length, greaterThan(1));
    expect(output.every((b) => b.length <= 37), isTrue);
    rpc.close();
  });
  test('STOP preempts pending confirm and late result cannot resurrect it',
      () async {
    final replies = <List<int>>[];
    final commands = <int>[];
    final rpc = BoardRpc(
        mtu: 247,
        write: (bytes) async {
          final f = RpcFrame.decode(bytes);
          commands.add(f.kind);
          if (f.kind == 3) {
            final b = utf8.encode(jsonEncode({
              'status': 200,
              'body': {'state': 'stopped', 'terminal': true}
            }));
            replies.add(RpcFrame(2, f.id, 0, b.length, b).encode());
          }
        },
        read: () async {
          if (replies.isEmpty) throw StateError('pending');
          return replies.removeAt(0);
        });
    final confirm = rpc.request({'operation': 'confirm', 'task_id': 'a' * 32});
    final rejected = expectLater(confirm, throwsStateError);
    await Future<void>.delayed(const Duration(milliseconds: 10));
    final stopped = await rpc.request({'operation': 'stop'});
    expect(stopped['state'], 'stopped');
    await rejected;
    expect(commands, contains(3));
    rpc.close();
  });
  test('ordinary requests queue until earlier response completes', () async {
    final frames = <RpcFrame>[], replies = <List<int>>[];
    final rpc = BoardRpc(
        mtu: 247,
        write: (b) async {
          frames.add(RpcFrame.decode(b));
        },
        read: () async {
          if (replies.isEmpty) throw StateError('pending');
          return replies.removeAt(0);
        });
    final a = rpc.request({'operation': 'status'}),
        b = rpc.request({'operation': 'status'});
    final both = Future.wait([a, b]);
    await Future<void>.delayed(const Duration(milliseconds: 10));
    expect(frames.length, 1);
    void reply(String id) {
      final data = utf8.encode(jsonEncode({
        'status': 200,
        'body': {'state': 'idle'}
      }));
      replies.add(RpcFrame(2, id, 0, data.length, data).encode());
    }

    reply(frames.first.id);
    await Future<void>.delayed(const Duration(milliseconds: 100));
    expect(frames.length, 2);
    reply(frames.last.id);
    await both;
    rpc.close();
  });
  test('STOP cancels active and queued requests before old writes resume',
      () async {
    final blocked = Completer<void>(),
        replies = <List<int>>[],
        frames = <RpcFrame>[];
    final rpc = BoardRpc(
        mtu: 26,
        write: (b) async {
          final f = RpcFrame.decode(b);
          frames.add(f);
          if (f.kind == 1) await blocked.future;
          if (f.kind == 3) {
            final data = utf8.encode(jsonEncode({
              'status': 200,
              'body': {'state': 'stopped', 'terminal': true}
            }));
            replies.add(RpcFrame(2, f.id, 0, data.length, data).encode());
          }
        },
        read: () async {
          if (replies.isEmpty) throw StateError('pending');
          return replies.removeAt(0);
        });
    final first = rpc.request({'operation': 'prepare', 'text': 'hello'});
    final a = expectLater(first, throwsStateError);
    final queued = rpc.request({'operation': 'status'});
    final b = expectLater(queued, throwsStateError);
    await Future<void>.delayed(Duration.zero);
    expect((await rpc.request({'operation': 'stop'}))['state'], 'stopped');
    blocked.complete();
    await a;
    await b;
    await Future<void>.delayed(const Duration(milliseconds: 10));
    expect(frames.map((f) => f.kind), [1, 3]);
    rpc.close();
  });
  test('late read after connection invalidation is rejected', () async {
    final reading = Completer<List<int>>();
    var live = true;
    String? id;
    final rpc = BoardRpc(
        mtu: 247,
        isCurrent: () => live,
        write: (b) async {
          id = RpcFrame.decode(b).id;
        },
        read: () => reading.future);
    final result = rpc.request({'operation': 'status'});
    final rejected = expectLater(result, throwsStateError);
    await Future<void>.delayed(Duration.zero);
    live = false;
    final data = utf8.encode(jsonEncode({
      'status': 200,
      'body': {'state': 'done'}
    }));
    reading.complete(RpcFrame(2, id!, 0, data.length, data).encode());
    await rejected;
    rpc.close();
  });
  test('timeout retires the in-flight last fragment before reporting failure',
      () async {
    final blocked = Completer<void>(),
        replies = <List<int>>[],
        frames = <RpcFrame>[];
    final rpc = BoardRpc(
        mtu: 247,
        requestTimeout: const Duration(milliseconds: 30),
        write: (b) async {
          final f = RpcFrame.decode(b);
          frames.add(f);
          if (f.kind == 1) await blocked.future;
          if (f.kind == 3) {
            final data = utf8.encode(jsonEncode({
              'status': 200,
              'body': {'state': 'stopped', 'terminal': true}
            }));
            replies.add(RpcFrame(2, f.id, 0, data.length, data).encode());
          }
        },
        read: () async {
          if (replies.isEmpty) throw StateError('pending');
          return replies.removeAt(0);
        });
    await expectLater(
        rpc.request({'operation': 'confirm', 'task_id': 'a' * 32}),
        throwsA(isA<TimeoutException>()));
    expect(frames.map((f) => f.kind), [1, 3]);
    expect(frames.last.id, frames.first.id);
    blocked.complete();
    await Future<void>.delayed(const Duration(milliseconds: 30));
    expect(frames.length, 2);
    rpc.close();
  });
  test(
      'old result and late writer error cannot acknowledge or cancel retirement',
      () async {
    final blocked = Completer<void>(),
        stopped = Completer<void>(),
        replies = <List<int>>[];
    String? target;
    var completed = false;
    final rpc = BoardRpc(
        mtu: 247,
        requestTimeout: const Duration(milliseconds: 300),
        write: (b) async {
          final f = RpcFrame.decode(b);
          target = f.id;
          if (f.kind == 1) await blocked.future;
          if (f.kind == 3) {
            final old = utf8.encode(jsonEncode({
              'status': 200,
              'body': {'state': 'queued', 'terminal': false}
            }));
            replies.add(RpcFrame(2, f.id, 0, old.length, old).encode());
            await stopped.future;
            final done = utf8.encode(jsonEncode({
              'status': 200,
              'body': {'state': 'stopped', 'terminal': true}
            }));
            replies.add(RpcFrame(2, f.id, 0, done.length, done).encode());
          }
        },
        read: () async {
          if (replies.isEmpty) throw StateError('pending');
          return replies.removeAt(0);
        });
    final request = rpc.request({'operation': 'confirm', 'task_id': 'a' * 32});
    final rejected = expectLater(request, throwsStateError);
    await Future<void>.delayed(Duration.zero);
    final stop = rpc.request({'operation': 'stop'}).then((v) {
      completed = true;
      return v;
    });
    blocked.completeError(StateError('late ATT failure'));
    await Future<void>.delayed(const Duration(milliseconds: 30));
    expect(target, isNotNull);
    expect(completed, isFalse);
    stopped.complete();
    expect((await stop)['state'], 'stopped');
    await rejected;
    rpc.close();
  });
  test(
      'inner ATT write timeout retires before failure and delayed delivery cannot resume',
      () async {
    final underlying = Completer<void>(),
        replies = <List<int>>[],
        frames = <RpcFrame>[];
    final rpc = BoardRpc(
        mtu: 247,
        requestTimeout: const Duration(milliseconds: 300),
        write: (b) {
          final f = RpcFrame.decode(b);
          frames.add(f);
          if (f.kind == 1) {
            return underlying.future.timeout(const Duration(milliseconds: 20));
          }
          final done = utf8.encode(jsonEncode({
            'status': 200,
            'body': {'state': 'stopped', 'terminal': true}
          }));
          replies.add(RpcFrame(2, f.id, 0, done.length, done).encode());
          return Future.value();
        },
        read: () async {
          if (replies.isEmpty) throw StateError('pending');
          return replies.removeAt(0);
        });
    await expectLater(
        rpc.request({'operation': 'confirm', 'task_id': 'a' * 32}),
        throwsA(isA<TimeoutException>()));
    expect(frames.map((f) => f.kind), [1, 3]);
    expect(frames.last.id, frames.first.id);
    underlying.complete();
    await Future<void>.delayed(const Duration(milliseconds: 30));
    expect(frames.length, 2);
    rpc.close();
  });
  test(
      'unacknowledged timeout retirement reports uncertainty and blocks new writes',
      () async {
    var writes = 0;
    final rpc = BoardRpc(
        mtu: 247,
        requestTimeout: const Duration(milliseconds: 20),
        write: (b) async {
          writes++;
        },
        read: () async => throw StateError('pending'));
    await expectLater(
        rpc.request({'operation': 'confirm', 'task_id': 'a' * 32}),
        throwsA(isA<TimeoutException>()
            .having((e) => e.message, 'message', contains('停止未确认'))));
    final before = writes;
    await expectLater(rpc.request({'operation': 'prepare', 'text': 'hello'}),
        throwsStateError);
    expect(writes, before);
    rpc.close();
  });
  test('malformed or oversized frames fail closed', () {
    expect(() => RpcFrame.decode(List.filled(21, 0)), throwsFormatException);
    expect(() => RpcFrame.decode(RpcFrame(2, 'a' * 32, 0, 8193, [1]).encode()),
        throwsFormatException);
  });
}
