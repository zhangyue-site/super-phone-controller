import 'dart:io';
import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/controller_local_vision.dart';
import 'controller_local_vision_test.dart' as fixture;

class HashRuntime extends fixture.Runtime {
  final String expected;
  HashRuntime(this.expected);
  @override
  Future<void> load(String path, String hash) async {
    expect(hash, expected);
    expect(hash, isNot('builtin'));
    expect(sha256.convert(await File(path).readAsBytes()).toString(), hash);
    await super.load(path, hash);
  }
}

void main() {
  test(
      'builtin SHA is used and metadata allows frame-bound inference without download',
      () async {
    final d = await Directory.systemTemp.createTemp('builtin-flow');
    final source = fixture.Source();
    final file = File.fromUri(d.uri.resolve('model.onnx'));
    await file.writeAsBytes(source.model);
    final hash = sha256.convert(source.model).toString();
    final runtime = HashRuntime(hash);
    final v = ControllerLocalVision(source,
        runtimeFactory: () => runtime,
        cacheDirectory: () async => d,
        builtinModel: () async => (path: file.path, hash: hash));
    try {
      await v.prepare();
      expect(v.ready, isTrue);
      expect(source.downloads, 0);
      expect(runtime.loads, 1);
      await v.observe('a' * 32);
      expect(source.submits, 1);
      expect(v.inferenceMs, 12.5);
    } finally {
      await v.close();
      await d.delete(recursive: true);
    }
  });
}
