import 'dart:io';
import 'dart:typed_data';
import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as image;
import 'package:pcflash/controller_model_runtime.dart';

void main() {
  final path = Platform.environment['CONTROLLER_MODEL_SMOKE'];
  test(
      'real private ONNX runs in controller inference isolate on synthetic JPEG',
      () async {
    final r = OrtButtonInference();
    final f = File(path!);
    final hash = sha256.convert(await f.readAsBytes()).toString();
    try {
      await r.load(path, hash);
      final pixels = image.Image(width: 320, height: 480);
      image.fill(pixels, color: image.ColorRgb8(96, 96, 96));
      final result = await r.infer(Uint8List.fromList(image.encodeJpg(pixels)));
      expect(result.inferenceMs, isNonNegative);
      expect(result.boxes.length, lessThanOrEqualTo(100));
      // Synthetic frame proves model loading/inference only, never a real phone click.
      // ignore: avoid_print
      print(
          'PRIVATE_MODEL_SMOKE synthetic=true boxes=${result.boxes.length} inference_ms=${result.inferenceMs}');
    } finally {
      await r.close();
    }
    await expectLater(r.infer(Uint8List(0)), throwsStateError);
  }, skip: path == null, timeout: const Timeout(Duration(seconds: 60)));
}
