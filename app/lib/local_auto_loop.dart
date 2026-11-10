import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'button_detector.dart';
import 'controller_builtin_model.dart';
import 'controller_model_runtime.dart';

void workbenchDiagnostic(String stage, {int count = 0, int value = 0}) {
  const channel = MethodChannel('pcflash/local-loop');
  unawaited(channel.invokeMethod<void>('diagnostic', {
    'stage': stage,
    'count': count,
    'value': value.clamp(0, 60000),
  }).catchError((_) {}));
}

/// Read-only workbench. Detections stay paired with the image they came from.
class LocalAutoLoopCard extends StatefulWidget {
  const LocalAutoLoopCard({super.key});

  @override
  State<LocalAutoLoopCard> createState() => _LocalAutoLoopCardState();
}

class _LocalAutoLoopCardState extends State<LocalAutoLoopCard> {
  static const _channel = MethodChannel('pcflash/local-loop');
  static const _limit = 10;
  bool _busy = false;
  Timer? _ocrPoll;
  String _ocrStatus = '连续文字识别未开始';
  bool _ocrActive = false, _ocrPending = false, _ocrReading = false;
  int _received = 0, _recognized = 0;
  String? _buttonRun;
  String? _ocrError;
  String _ocrPreview = "";
  @override
  void initState() {
    super.initState();
    _ocrPoll =
        Timer.periodic(const Duration(seconds: 1), (_) => _readOcrStatus());
    unawaited(_readOcrStatus());
  }

  Future<void> _billOcr(bool start,
      {bool delayed = false, int? autoEpoch}) async {
    if (_ocrPending) return;
    setState(() {
      _ocrPending = true;
      _ocrError = null;
    });
    try {
      if (start) {
        final ok = await _channel.invokeMethod<bool>('startBillOcr', {
          if (delayed) 'delayed': true,
          if (autoEpoch != null) 'autoEpoch': autoEpoch,
        });
        if (ok != true && mounted) {
          setState(() => _ocrStatus = '未开始，请检查解锁、屏幕共享或上一轮识别');
        }
      } else {
        await _channel.invokeMethod<void>('stopBillOcr');
      }
      await _readOcrStatus();
    } catch (_) {
      if (mounted) setState(() => _ocrError = '无法读取识别状态，请检查屏幕共享');
    } finally {
      if (mounted) setState(() => _ocrPending = false);
    }
  }

  Future<void> _readOcrStatus() async {
    if (_ocrReading) return;
    _ocrReading = true;
    try {
      final status = await _channel.invokeMethod<String>('billOcrStatus');
      final meta =
          await _channel.invokeMapMethod<String, dynamic>('recognitionStatus');
      if (mounted) {
        setState(() {
          if (status != null) _ocrStatus = status;
          final currentIsOcr = meta?['source'] == 'ocr';
          _ocrActive = currentIsOcr && meta?['active'] == true;
          final legacyOcr = currentIsOcr ? meta : null;
          _received =
              ((meta?['ocrReceived'] ?? legacyOcr?['received']) as int?) ?? 0;
          _recognized =
              ((meta?['ocrCount'] ?? legacyOcr?['count']) as int?) ?? 0;
          _ocrPreview =
              ((meta?['ocrPreview'] ?? legacyOcr?['preview']) as String?) ?? '';
        });
        final epoch = meta?['autoEpoch'];
        if (epoch is int && !_busy && !_ocrPending && !_ocrActive) {
          switch (meta?['autoStep']) {
            case 'ocr':
              unawaited(_billOcr(true, autoEpoch: epoch));
            case 'buttons':
              unawaited(_run(autoEpoch: epoch));
          }
        }
      }
    } catch (_) {
      if (mounted) setState(() => _ocrError = '识别状态暂不可读');
    } finally {
      _ocrReading = false;
    }
  }

  bool _stopped = false;
  int _count = 0;
  String _status = '等待开始';
  Uint8List? _preview;
  List<ButtonBox> _boxes = [];
  double? _inferenceMs;
  double _aspectRatio = 9 / 16;

  @override
  void dispose() {
    _stopped = true;
    _ocrPoll?.cancel();
    final run = _buttonRun;
    if (run != null) {
      unawaited(_channel.invokeMethod<void>('endButtonRecognition',
          {'run': run, 'reason': 'stopped'}).catchError((_) {}));
    }
    super.dispose();
  }

  void _diagnostic(String stage, [int value = 0]) =>
      workbenchDiagnostic(stage, count: _count, value: value);

  Future<void> _run({int? autoEpoch}) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _stopped = false;
      _count = 0;
      _preview = null;
      _inferenceMs = null;
      _boxes = [];
      _status = '正在加载内置按钮模型';
    });
    _diagnostic('start');
    final runtime = OrtButtonInference();
    String outcome = '本轮已停止';
    String reason = 'stopped';
    try {
      final lease = await _channel.invokeMapMethod<String, dynamic>(
          'beginButtonRecognition',
          autoEpoch == null ? null : {'autoEpoch': autoEpoch});
      final run = lease?['run'];
      final epoch = lease?['epoch'];
      final minimumFrame = lease?['afterFrame'];
      if (run is! String || epoch is! int || minimumFrame is! int) {
        throw const FormatException('未建立识别会话');
      }
      _buttonRun = run;

      final model = await BuiltinModelLoader.prepare();
      if (_stopped) return;
      await runtime.load(model.path, model.hash);
      _diagnostic('loaded');
      int? lastFrame;
      var lastProgress = Duration.zero;
      final elapsed = Stopwatch()..start();
      while (!_stopped &&
          _count < _limit &&
          elapsed.elapsed < const Duration(seconds: 90)) {
        final frame = await _channel.invokeMapMethod<String, dynamic>(
          'latestFrame',
          {'run': run},
        );
        if (_stopped) break;
        final jpeg = frame?['jpeg'];
        final id = frame?['frameId'];
        final age = frame?['ageMs'];
        final width = frame?['width'];
        final height = frame?['height'];
        if (frame?['available'] != true ||
            id is! int ||
            id <= minimumFrame ||
            age is! int ||
            age < 0 ||
            age > 2500 ||
            jpeg is! Uint8List ||
            jpeg.isEmpty ||
            jpeg.length > 524288 ||
            width is! int ||
            height is! int ||
            width < 1 ||
            height < 1) {
          _diagnostic(
              frame?['available'] != true
                  ? 'unavailable'
                  : age is int && age > 2500
                      ? 'stale'
                      : 'invalid',
              age is int ? age : 0);
          if (elapsed.elapsed - lastProgress >= const Duration(seconds: 12)) {
            reason = 'frame_timeout';
            outcome = '没有收到新的共享帧，已停止';
            break;
          }
          await Future<void>.delayed(const Duration(milliseconds: 250));
          continue;
        }
        if (frame?['captureEpoch'] != epoch) {
          reason = 'error';
          outcome = '共享会话已改变，本轮已停止';
          break;
        }
        if (lastFrame != null && id < lastFrame) {
          _diagnostic('order');
          outcome = '帧顺序异常，请重新开始';
          break;
        }
        if (lastFrame != id) {
          final result = await runtime.infer(jpeg);
          if (_stopped || !mounted) break;
          final recorded =
              await _channel.invokeMethod<bool>('recordButtonRecognition', {
            'run': run,
            'frameId': id,
            'age': age,
            'epoch': epoch,
            'width': width,
            'height': height,
            'ms': result.inferenceMs.round(),
            'boxes': result.boxes.length,
          });
          if (_stopped || !mounted) break;
          if (recorded != true) throw const FormatException('识别帧未被本轮接收');
          lastFrame = id;
          lastProgress = elapsed.elapsed;
          setState(() {
            _count++;
            _preview = jpeg;
            _aspectRatio = width / height;
            _boxes = result.boxes;
            _inferenceMs = result.inferenceMs;
            _status = '正在识别';
          });
          _diagnostic('frame', result.inferenceMs.round());
          _diagnostic('boxes', result.boxes.length);
        } else {
          _diagnostic('wait', age);
          if (elapsed.elapsed - lastProgress >= const Duration(seconds: 12)) {
            reason = 'frame_timeout';
            outcome = '没有收到新的共享帧，已停止';
            break;
          }
        }
        if (_count < _limit) {
          await Future<void>.delayed(const Duration(seconds: 1));
        }
      }
      if (!_stopped) {
        if (_count == _limit) {
          _diagnostic('done');
          reason = 'done';
          outcome = '本轮识别完成';
        } else if (elapsed.elapsed >= const Duration(seconds: 90)) {
          _diagnostic('timeout');
          reason = 'timeout';
          outcome = '已达到本轮时间上限';
        }
      }
    } catch (_) {
      if (!_stopped) _diagnostic('failure');
      reason = _stopped ? 'stopped' : 'error';
      outcome = _stopped ? '本轮已停止' : '识别失败，请检查模型或屏幕共享';
    } finally {
      if (_stopped) _diagnostic('stop');
      final run = _buttonRun;
      _buttonRun = null;
      if (run != null) {
        try {
          await _channel.invokeMethod<void>('endButtonRecognition',
              {'run': run, 'reason': _stopped ? 'stopped' : reason});
        } catch (_) {}
      }
      try {
        await runtime.close();
      } finally {
        if (mounted) {
          setState(() {
            _busy = false;
            _status = outcome;
          });
        }
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final preview = _preview;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('本地模型工作台', style: Theme.of(context).textTheme.titleMedium),
            const Text('保持解锁和屏幕共享。任意页面都可连续识别 10 个新帧，不会点击或保存。'),
            Semantics(liveRegion: true, child: Text(_ocrStatus)),
            if (_ocrError != null)
              Text(_ocrError!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error)),
            Text('本轮已识别 $_recognized / 10 帧 · 106 已接收 $_received / 10 帧'),
            Wrap(
              spacing: 8,
              children: [
                FilledButton(
                    onPressed: _busy || _ocrActive || _ocrPending
                        ? null
                        : () => _billOcr(true),
                    child: const Text('开始连续文字识别')),
                OutlinedButton(
                    onPressed: _ocrPending || !_ocrActive
                        ? null
                        : () => _billOcr(false),
                    child: const Text('停止文字识别')),
              ],
            ),
            TextButton(
                onPressed: _busy || _ocrActive || _ocrPending
                    ? null
                    : () => _billOcr(true, delayed: true),
                child: const Text('8 秒后开始，留时间切换页面')),
            if (_ocrPreview.isNotEmpty) ...[
              const Text('最近一帧识别文字'),
              SelectableText(_ocrPreview),
            ],
            const Divider(),
            const Text('按钮识别每轮最多 10 个新帧或 90 秒。'),
            Text(_status),
            Text('已识别 $_count / $_limit 帧'),
            if (_inferenceMs != null)
              Text(
                '候选 ${_boxes.length} 个 · ${_inferenceMs!.toStringAsFixed(0)} ms',
              ),
            if (preview != null)
              Center(
                child: SizedBox(
                  height: 200,
                  child: AspectRatio(
                    aspectRatio: _aspectRatio,
                    child: Stack(
                      fit: StackFit.expand,
                      children: [
                        Image.memory(
                          preview,
                          fit: BoxFit.fill,
                          gaplessPlayback: true,
                        ),
                        CustomPaint(painter: _CandidatePainter(_boxes)),
                      ],
                    ),
                  ),
                ),
              ),
            Wrap(
              spacing: 8,
              children: [
                FilledButton(
                  onPressed:
                      _busy || _ocrActive || _ocrPending ? null : () => _run(),
                  child: const Text('开始一轮识别'),
                ),
                OutlinedButton(
                  onPressed: _busy && !_stopped
                      ? () {
                          setState(() {
                            _stopped = true;
                            _status = '正在停止';
                          });
                          final run = _buttonRun;
                          if (run != null) {
                            unawaited(_channel.invokeMethod<void>(
                                'endButtonRecognition', {
                              'run': run,
                              'reason': 'stopped'
                            }).catchError((_) {}));
                          }
                        }
                      : null,
                  child: const Text('停止'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _CandidatePainter extends CustomPainter {
  final List<ButtonBox> boxes;
  const _CandidatePainter(this.boxes);

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = Colors.lightGreenAccent
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2;
    for (final box in boxes) {
      canvas.drawRect(
        Rect.fromLTWH(
          box.x * size.width,
          box.y * size.height,
          box.width * size.width,
          box.height * size.height,
        ),
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(_CandidatePainter oldDelegate) =>
      oldDelegate.boxes != boxes;
}
