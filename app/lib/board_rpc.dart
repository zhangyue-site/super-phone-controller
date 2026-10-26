import 'dart:async';
import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';

class RpcFrame {
  final int kind, offset, total;
  final String id;
  final List<int> payload;
  RpcFrame(this.kind, this.id, this.offset, this.total, this.payload);
  List<int> encode() {
    if (!RegExp(r'^[0-9a-f]{32}$').hasMatch(id)) {
      throw const FormatException('请求标识无效');
    }
    final b = Uint8List(22 + payload.length);
    b[0] = 1;
    b[1] = kind;
    for (var i = 0; i < 16; i++) {
      b[i + 2] = int.parse(id.substring(i * 2, i * 2 + 2), radix: 16);
    }
    final view = ByteData.sublistView(b);
    view.setUint16(18, offset, Endian.little);
    view.setUint16(20, total, Endian.little);
    b.setRange(22, b.length, payload);
    return b;
  }

  factory RpcFrame.decode(List<int> value) {
    if (value.length < 22 ||
        value[0] != 1 ||
        ![1, 2, 3, 4].contains(value[1])) {
      throw const FormatException('蓝牙控制帧无效');
    }
    final b = Uint8List.fromList(value),
        v = ByteData.sublistView(Uint8List.fromList(value));
    final offset = v.getUint16(18, Endian.little),
        total = v.getUint16(20, Endian.little);
    if (total > 8192 || offset > total || b.length - 22 > total - offset) {
      throw const FormatException('蓝牙控制帧超限');
    }
    return RpcFrame(
        b[1],
        b.sublist(2, 18).map((n) => n.toRadixString(16).padLeft(2, '0')).join(),
        offset,
        total,
        b.sublist(22));
  }
}

class _Reply {
  final bool stopping;
  _Reply(this.stopping);
  Future<bool>? retirement;
  final Completer<Map<String, dynamic>> done = Completer();
  final List<int> bytes = [];
  int? total;
}

/// One BLE reader dispatches responses by request id, including during STOP.
class BoardRpc {
  final Future<void> Function(List<int>) write;
  final Future<List<int>> Function() read;
  final bool Function()? isCurrent;
  final int mtu;
  final _pending = <String, _Reply>{};
  bool _pumping = false, _closed = false;
  int _generation = 0;
  Future<void> _tail = Future.value();
  final Duration requestTimeout;
  BoardRpc(
      {required this.write,
      required this.read,
      required this.mtu,
      this.isCurrent,
      this.requestTimeout = const Duration(seconds: 30)});
  bool get _live => !_closed && (isCurrent?.call() ?? true);
  void _fail(String id, Object error) {
    final p = _pending.remove(id);
    if (p != null && !p.done.isCompleted) p.done.completeError(error);
  }

  void _cancelOlder() {
    for (final id in _pending.keys.toList()) {
      _fail(id, StateError('停止已取消旧请求'));
    }
  }

  Future<Map<String, dynamic>> request(Map<String, dynamic> body) {
    final stopping = body['operation'] == 'stop';
    if (stopping) {
      return _requestStop(_pending.isEmpty ? null : _pending.keys.first);
    }
    final generation = _generation;
    final result = _tail.then((_) {
      if (!_live || generation != _generation) throw StateError('控制请求已取消');
      return _send(body, generation);
    });
    _tail = result.then<void>((_) {}, onError: (Object _, StackTrace __) {});
    return result;
  }

  Future<Map<String, dynamic>> _requestStop(String? cancelledId) {
    _generation++;
    _cancelOlder();
    final result = _send({'operation': 'stop'}, _generation, cancelledId);
    _tail = result.then<void>((_) {}, onError: (Object _, StackTrace __) {});
    return result;
  }

  Future<bool> _retire(String id, _Reply reply, Object error) {
    return reply.retirement ??= () async {
      if (!identical(_pending[id], reply)) return false;
      // Do not complete the failed request before the retirement ACK.
      _pending.remove(id);
      Object failure = error;
      var acknowledged = true;
      try {
        await _requestStop(id);
      } catch (_) {
        acknowledged = false;
        close();
        failure = TimeoutException('停止未确认，连接已封锁；请使用板上停止按钮，必要时重启控制板');
      }
      if (!reply.done.isCompleted) reply.done.completeError(failure);
      return acknowledged;
    }();
  }

  Future<Map<String, dynamic>> _send(Map<String, dynamic> body, int generation,
      [String? cancelledId]) {
    if (!_live) return Future.error(StateError('蓝牙连接已断开'));
    final stopping = body['operation'] == 'stop';
    final random = Random.secure();
    final id = cancelledId ??
        List.generate(16, (_) => random.nextInt(256))
            .map((n) => n.toRadixString(16).padLeft(2, '0'))
            .join();
    final bytes = utf8.encode(jsonEncode(body));
    if (bytes.length > 2048 || mtu < 26) {
      throw const FormatException('指令过长或蓝牙传输容量不足');
    }
    final reply = _Reply(stopping);
    _pending[id] = reply;
    // Attach timeout/error handler before a synchronous cancellation can occur.
    final result =
        reply.done.future.timeout(requestTimeout, onTimeout: () async {
      if (stopping) {
        _pending.remove(id);
        close();
        throw TimeoutException('停止尚未确认，连接已封锁；请使用板上停止按钮；必要时重启控制板后重新连接');
      }
      if (!await _retire(id, reply, TimeoutException('请求超时，旧请求已撤销；不会自动重放'))) {
        throw TimeoutException('停止未确认，连接已封锁；请使用板上停止按钮，必要时重启控制板');
      }
      throw TimeoutException('请求超时，旧请求已撤销；不会自动重放');
    });
    // Return immediately so callers observe cancellation even while an ATT write waits.
    unawaited(() async {
      try {
        if (stopping) {
          await write(RpcFrame(3, id, 0, 0, []).encode());
        } else {
          final step = min(180, mtu - 25);
          for (var offset = 0; offset < bytes.length; offset += step) {
            if (!_live ||
                generation != _generation ||
                !_pending.containsKey(id)) {
              throw StateError('控制请求已取消');
            }
            final end = min(offset + step, bytes.length);
            await write(RpcFrame(
                    1, id, offset, bytes.length, bytes.sublist(offset, end))
                .encode());
          }
        }
      } catch (error) {
        if (identical(_pending[id], reply)) {
          if (stopping) {
            _fail(id, error);
            close();
          } else {
            await _retire(id, reply, error);
          }
        }
      }
      _pump();
    }());
    return result;
  }

  Future<void> _pump() async {
    if (_pumping) return;
    _pumping = true;
    try {
      while (_pending.isNotEmpty) {
        if (!_live) {
          _cancelOlder();
          break;
        }
        try {
          final readingGeneration = _generation;
          final raw = await read().timeout(const Duration(seconds: 2));
          if (!_live) {
            _cancelOlder();
            break;
          }
          // A read started before STOP may finish afterwards. Only a current
          // request id may survive that generation change.
          if (readingGeneration != _generation) {
            try {
              if (!_pending.containsKey(RpcFrame.decode(raw).id)) continue;
            } on FormatException {
              continue;
            }
          }
          final f = RpcFrame.decode(raw);
          if (f.kind == 4) continue; // informational connection hello
          final p = _pending[f.id];
          if (f.kind != 2 || p == null) continue;
          if (f.total < 2 ||
              f.offset != p.bytes.length ||
              (p.total != null && p.total != f.total)) {
            _fail(f.id, const FormatException('蓝牙响应分片顺序不符'));
            continue;
          }
          p.total = f.total;
          p.bytes.addAll(f.payload);
          if (p.bytes.length == f.total) {
            final value = jsonDecode(utf8.decode(p.bytes));
            if (value is! Map ||
                value['status'] is! int ||
                value['body'] is! Map) {
              _fail(f.id, const FormatException('板端响应格式无效'));
              continue;
            }
            final data = Map<String, dynamic>.from(value['body'] as Map);
            if (p.stopping &&
                (data['state'] != 'stopped' || data['terminal'] != true)) {
              p.bytes.clear();
              p.total = null;
              continue;
            }
            _pending.remove(f.id);
            if (value['status'] != 200) {
              p.done.completeError(FormatException(
                  data['reply'] as String? ?? '板子未完成请求，请检查网络和连接'));
            } else {
              p.done.complete(data);
            }
          }
        } on FormatException catch (error) {
          for (final id in _pending.keys.toList()) {
            _fail(id, error);
          }
        } catch (_) {
          // ATT pending is expected while the board relays to cloud.
          await Future<void>.delayed(const Duration(milliseconds: 60));
        }
      }
    } finally {
      _pumping = false;
      if (_pending.isNotEmpty) _pump();
    }
  }

  void close() {
    _closed = true;
    _generation++;
    _cancelOlder();
  }
}
