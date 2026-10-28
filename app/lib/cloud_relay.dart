import "dart:async";

/// Opaque signed packets only. No device key, action planning or ADB fallback.
class CloudRelay {
  final Future<Map<String, dynamic>> Function(String, Map<String, dynamic>)
      post;
  final Future<Map<String, dynamic>> Function() read;
  final Future<void> Function(List<int>) write;
  final Future<void> Function() disconnect;
  final void Function(Object) onError;
  final Future<void> Function(bool hid)? beforeModeChange;
  Timer? _timer;
  String? _nonce;
  bool _busy = false, _closed = false;
  CloudRelay(
      {required this.post,
      required this.read,
      required this.write,
      required this.disconnect,
      required this.onError,
      this.beforeModeChange});
  bool get isClosed => _closed;

  Future<void> start() async {
    if (_closed || _timer != null) throw StateError("控制会话不可重复启动");
    final initial = await read();
    final nonce = initial["nonce"];
    if (nonce is! String || !RegExp(r"^[0-9a-f]{32}$").hasMatch(nonce)) {
      throw const FormatException("板子会话无效");
    }
    await post("attach", {"receipt": initial});
    _nonce = nonce;
    if (_closed) {
      try {
        await post('detach', {'nonce': nonce});
      } catch (_) {}
      throw StateError('控制连接已结束');
    }
    _timer = Timer.periodic(const Duration(milliseconds: 500), (_) => _tick());
  }

  Future<void> _tick() async {
    if (_busy || _closed) return;
    _busy = true;
    try {
      final command = await post("poll", {"nonce": _nonce});
      if (_closed || command["state"] != "action") return;
      final packet = command["packet"],
          seq = command["seq"],
          op = command["op"];
      if (packet is! String ||
          !RegExp(r"^[0-9a-f]{96}$").hasMatch(packet) ||
          seq is! int ||
          op is! int ||
          op < 1 ||
          op > 7) {
        throw const FormatException("云端动作格式无效");
      }
      final bytes = List.generate(
          48, (i) => int.parse(packet.substring(i * 2, i * 2 + 2), radix: 16));
      if (op == 5 || op == 6 || op == 7) {
        await beforeModeChange?.call(op == 6);
        if (_closed) return;
      }
      // Exactly one ATT write. No retry after a timeout or uncertain receipt.
      await write(bytes).timeout(const Duration(seconds: 5));
      final until = DateTime.now().add(const Duration(seconds: 10));
      Map<String, dynamic>? receipt;
      while (!_closed && DateTime.now().isBefore(until)) {
        final r = await read().timeout(const Duration(seconds: 2));
        if (r["nonce"] != _nonce) throw StateError("板子会话已改变");
        if (r["seq"] == seq &&
            r["op"] == op &&
            r["busy"] == 0 &&
            r["result"] != 1 &&
            r["result"] != 2) {
          if (op != 6 && op != 7 ||
              r["result"] != (op == 6 ? 7 : 8) ||
              r["ready"] == 1 && r["hid"] == (op == 6 ? 1 : 0)) {
            receipt = r;
            break;
          }
        }
        await Future<void>.delayed(const Duration(milliseconds: 100));
      }
      if (receipt == null) throw TimeoutException("板端回执未确认，不会重发");
      final result = await post(
          "ack", {"nonce": _nonce, "id": command["id"], "receipt": receipt});
      if (result["state"] != "acknowledged") throw StateError("板端动作失败");
      if (op == 5) await close();
    } catch (error) {
      await close();
      onError(error);
    } finally {
      _busy = false;
    }
  }

  Future<void> close() async {
    if (_closed) return;
    _closed = true;
    _timer?.cancel();
    // Disconnect releases HID even if cloud is unavailable.
    try {
      await disconnect();
    } finally {
      if (_nonce != null) {
        try {
          await post("detach", {"nonce": _nonce});
        } catch (_) {}
      }
    }
  }
}
