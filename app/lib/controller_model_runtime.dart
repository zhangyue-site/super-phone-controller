import 'dart:async';
import 'dart:io';
import 'dart:isolate';
import 'dart:typed_data';
import 'package:crypto/crypto.dart';
import 'package:onnxruntime_plus/onnxruntime_plus.dart';
import 'button_detector.dart';

class ButtonInferenceResult {
  final List<ButtonBox> boxes;
  final double inferenceMs;
  const ButtonInferenceResult(this.boxes, this.inferenceMs);
}

abstract interface class ButtonInference {
  Future<void> load(String path, String sha256);
  Future<ButtonInferenceResult> infer(Uint8List jpeg);
  Future<void> close();
}

/// One persistent isolate owns every native pointer and its lifecycle.
class OrtButtonInference implements ButtonInference {
  Isolate? _isolate;
  ReceivePort? _receive;
  SendPort? _send;
  StreamSubscription<dynamic>? _subscription;
  Completer<void>? _opening;
  Completer<ButtonInferenceResult>? _pending;
  Completer<void>? _closing;
  bool _closed = false, _workerEnded = false;
  int _sequence = 0;
  @override
  Future<void> load(String path, String hash) async {
    if (_closed || _opening != null) throw StateError('推理会话不可重复加载');
    _opening = Completer<void>();
    _receive = ReceivePort();
    _subscription = _receive!.listen((dynamic value) {
      if (value == null || value is List) {
        _workerEnded = true;
        if (!(_closing?.isCompleted ?? true)) _closing!.complete();
        if (!_opening!.isCompleted) {
          _opening!.completeError(const FormatException('本机推理进程已结束'));
        }
        if (_pending != null && !_pending!.isCompleted) {
          _pending!.completeError(StateError('本机推理进程已结束'));
        }
        return;
      }
      if (value is! Map) return;
      if (value['closed'] == true) {
        if (!(_closing?.isCompleted ?? true)) _closing!.complete();
        return;
      }
      if (value['ready'] == true) {
        _send = value['port'] as SendPort;
        if (!_opening!.isCompleted) _opening!.complete();
        if (_closed) _send!.send({'close': true});
        return;
      }
      if (value['error'] != null) {
        if (value['fatal'] == true) _workerEnded = true;
        if (_closed) {
          // A frame error precedes the queued close; only fatal release,
          // close ACK or worker exit can acknowledge native cleanup.
          if (value['fatal'] == true) {
            if (!(_closing?.isCompleted ?? true)) _closing!.complete();
            if (!_opening!.isCompleted) _opening!.complete();
          }
          return;
        }
        final error = FormatException(value['error'] as String);
        if (!_opening!.isCompleted) _opening!.completeError(error);
        if (_pending != null && !_pending!.isCompleted) {
          _pending!.completeError(error);
        }
        return;
      }
      if (_closed) return;
      if (value['sequence'] == _sequence &&
          _pending != null &&
          !_pending!.isCompleted) {
        try {
          final ms = value['inferenceMs'];
          if (ms is! num || !ms.isFinite || ms < 0) {
            throw const FormatException('本机推理时间无效');
          }
          final boxes = (value['boxes'] as List)
              .map((b) => ButtonBox.parse(b as Map))
              .toList();
          if (boxes.length > 100) throw const FormatException('本机检测结果过多');
          _pending!.complete(ButtonInferenceResult(boxes, ms.toDouble()));
        } catch (e) {
          _pending!.completeError(e);
        }
      }
    });
    try {
      _isolate = await Isolate.spawn(_worker, [_receive!.sendPort, path, hash], onError: _receive!.sendPort, onExit: _receive!.sendPort);
      await _opening!.future.timeout(const Duration(seconds: 30));
      if (_closed || _send == null) throw StateError('推理已停止');
    } catch (_) {
      await close();
      rethrow;
    }
  }

  @override
  Future<ButtonInferenceResult> infer(Uint8List jpeg) async {
    if (_closed || _send == null) throw StateError('本机模型尚未加载');
    if (_pending != null) throw StateError('已有本机推理在进行');
    if (jpeg.isEmpty || jpeg.length > 524288) {
      throw const FormatException('共享画面大小无效');
    }
    final pending = Completer<ButtonInferenceResult>();
    _pending = pending;
    _send!.send({
      'sequence': ++_sequence,
      'jpeg': TransferableTypedData.fromList([jpeg])
    });
    try {
      return await pending.future.timeout(const Duration(seconds: 10));
    } finally {
      if (identical(_pending, pending)) _pending = null;
    }
  }

  @override
  Future<void> close() async {
    if (_closed) return;
    _closed = true;
    final pending = _pending;
    _pending = null;
    if (pending != null && !pending.isCompleted) {
      pending.completeError(StateError('推理已停止'));
    }
    _closing = Completer<void>();
    _send?.send({'close': true});
    if (_opening != null && !_workerEnded) {
      try {
        await _closing!.future.timeout(const Duration(seconds: 30));
      } catch (_) {}
    }
    _isolate?.kill(priority: Isolate.immediate);
    _isolate = null;
    await _subscription?.cancel();
    _receive?.close();
    _receive = null;
    _send = null;
  }
}

void _worker(List<Object> args) {
  final host = args[0] as SendPort,
      path = args[1] as String,
      expected = args[2] as String;
  OrtSession? session;
  OrtSessionOptions? options;
  ReceivePort? port;
  void release() {
    session?.release();
    session = null;
    options?.release();
    options = null;
    OrtEnv.instance.release();
  }

  try {
    final model = File(path);
    if (model.lengthSync() > 32 * 1024 * 1024 ||
        sha256.convert(model.readAsBytesSync()).toString() != expected) {
      throw const FormatException('本机模型完整性校验失败');
    }
    OrtEnv.instance
        .init(level: OrtLoggingLevel.error, logId: 'controller-button');
    options = OrtSessionOptions()
      ..setIntraOpNumThreads(2)
      ..setInterOpNumThreads(1)
      ..setSessionGraphOptimizationLevel(GraphOptimizationLevel.ortEnableAll);
    session = OrtSession.fromFile(model, options!);
    if (session!.inputNames.length != 1 ||
        session!.inputNames.single != 'images' ||
        session!.outputNames.length != 1) {
      throw const FormatException('本机模型输入接口不兼容');
    }
    // Validate real output schema before reporting a usable runtime.
    final zeros = OrtValueTensor.createTensorWithDataList(
        Float32List(3 * 320 * 320), [1, 3, 320, 320]);
    final warmOptions = OrtRunOptions();
    List<OrtValue?>? warm;
    try {
      warm = session!.run(warmOptions, {'images': zeros});
      decodeButtonOutput(warm.single?.value);
    } finally {
      zeros.release();
      warmOptions.release();
      warm?.forEach((v) => v?.release());
    }
    port = ReceivePort();
    host.send({'ready': true, 'port': port.sendPort});
    port.listen((dynamic value) {
      if (value is! Map) return;
      if (value['close'] == true) {
        release();
        port?.close();
        host.send({'closed': true});
        return;
      }
      final sequence = value['sequence'];
      try {
        final jpeg = (value['jpeg'] as TransferableTypedData)
            .materialize()
            .asUint8List();
        final data = preprocessButtonJpeg(jpeg);
        final input =
            OrtValueTensor.createTensorWithDataList(data, [1, 3, 320, 320]);
        final runOptions = OrtRunOptions();
        List<OrtValue?>? outputs;
        try {
          final clock = Stopwatch()..start();
          outputs = session!.run(runOptions, {'images': input});
          clock.stop();
          final boxes = decodeButtonOutput(outputs.single?.value);
          host.send({
            'sequence': sequence,
            'inferenceMs': clock.elapsedMicroseconds / 1000.0,
            'boxes': boxes.map((b) => b.toJson()).toList()
          });
        } finally {
          input.release();
          runOptions.release();
          outputs?.forEach((v) => v?.release());
        }
      } catch (_) {
        host.send({'sequence': sequence, 'error': '本机模型识别失败，请检查模型兼容性后重试'});
      }
    });
  } catch (_) {
    try {
      release();
    } catch (_) {}
    host.send({'error': '本机模型无法加载，模型或运行库不兼容', 'fatal': true});
    port?.close();
  }
}
