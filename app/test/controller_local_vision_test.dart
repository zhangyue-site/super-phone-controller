import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/button_detector.dart';
import 'package:pcflash/controller_local_vision.dart';
import 'package:pcflash/controller_model_runtime.dart';

class Source implements LocalVisionSource {
  @override
  bool isPaired = true;
  @override
  bool authorized = true;
  final model = Uint8List.fromList([1, 2, 3]);
  final jpeg = Uint8List.fromList([9, 8, 7]);
  int downloads = 0, submits = 0;
  bool corrupt = false;
  @override
  Future<Uint8List> localModelBytes(ButtonModelManifest m) async {
    downloads++;
    return corrupt ? Uint8List.fromList([0, 0, 0]) : model;
  }

  @override
  Future<Map<String, dynamic>> localVision(
      String op, Map<String, dynamic> body) async {
    if (op == 'manifest') {
      return {
        'available': true,
        'format': 'onnx',
        'version': 'v3',
        'sha256': sha256.convert(model).toString(),
        'size': 3,
        'inputWidth': 320,
        'inputHeight': 320,
        'outputLayout': 'xywh-score',
        'preprocess': 'stretch-rgb-0-1'
      };
    }
    if (op == 'frame') {
      return {
        'task_id': 'a' * 32,
        'frame_id': sha256.convert(jpeg).toString(),
        'sequence': 1,
        'barrier': 'b' * 32,
        'width': 320,
        'height': 480,
        'jpegBase64': base64Encode(jpeg)
      };
    }
    submits++;
    expect(body['sequence'], 1);
    return {'accepted': true};
  }
}

class Runtime implements ButtonInference {
  int loads = 0;
  bool closed = false;
  Completer<ButtonInferenceResult>? pending;
  @override
  Future<void> load(String p, String h) async {
    loads++;
  }

  @override
  Future<ButtonInferenceResult> infer(Uint8List jpeg) async => pending == null
      ? const ButtonInferenceResult([ButtonBox(.1, .1, .2, .2, .9)], 12.5)
      : pending!.future;
  @override
  Future<void> close() async {
    closed = true;
  }
}

void main() {
  test(
      'paired controller validates private model cache then submits frame-bound local observations',
      () async {
    final d = await Directory.systemTemp.createTemp('controller-model-test');
    final source = Source(), runtime = Runtime();
    final v = ControllerLocalVision(source,
        runtimeFactory: () => runtime, cacheDirectory: () async => d);
    try {
      await v.prepare();
      expect(v.ready, isTrue);
      expect(source.downloads, 1);
      await v.observe('a' * 32);
      expect(source.submits, 1);
      expect(v.inferenceMs, 12.5);
      expect(v.boxCount, 1);
    } finally {
      await v.close();
      await d.delete(recursive: true);
    }
  });
  test(
      'target role never fetches a model and corrupted download cannot load native runtime',
      () async {
    final d = await Directory.systemTemp.createTemp('controller-model-test');
    final source = Source()..isPaired = false, runtime = Runtime();
    final v = ControllerLocalVision(source,
        runtimeFactory: () => runtime, cacheDirectory: () async => d);
    try {
      await v.prepare();
      expect(source.downloads, 0);
      expect(runtime.loads, 0);
      source.isPaired = true;
      source.corrupt = true;
      await v.prepare();
      expect(v.ready, isFalse);
      expect(v.error, isNotNull);
      expect(runtime.loads, 0);
    } finally {
      await v.close();
      await d.delete(recursive: true);
    }
  });
  test('STOP discards inference completion instead of publishing late boxes',
      () async {
    final d = await Directory.systemTemp.createTemp('controller-model-test');
    final source = Source(),
        runtime = Runtime()..pending = Completer<ButtonInferenceResult>();
    final v = ControllerLocalVision(source,
        runtimeFactory: () => runtime, cacheDirectory: () async => d);
    try {
      await v.prepare();
      final f = v.observe('a' * 32);
      await Future<void>.delayed(const Duration(milliseconds: 10));
      v.suspend();
      runtime.pending!.complete(const ButtonInferenceResult([], 8));
      await f;
      expect(source.submits, 0);
      expect(v.ready, isFalse);
      expect(v.inferenceMs, isNull);
    } finally {
      await v.close();
      await d.delete(recursive: true);
    }
  });
}
