import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter/services.dart';
import 'package:path_provider/path_provider.dart';

class BuiltinModelLoader {
  static const _name = 'bt_v10_int8.onnx';

  static Future<String> getModelPath() async => (await prepare()).path;

  static Future<({String path, String hash})> prepare() async {
    final data = await rootBundle.load('assets/$_name');
    final bytes =
        data.buffer.asUint8List(data.offsetInBytes, data.lengthInBytes);
    final hash = sha256.convert(bytes).toString();
    final cache = await getApplicationCacheDirectory();
    final directory = Directory('${cache.path}/controller-models');
    await directory.create(recursive: true);
    final model = File('${directory.path}/builtin-$hash-$_name');
    if (!await model.exists() ||
        sha256.convert(await model.readAsBytes()).toString() != hash) {
      await model.writeAsBytes(bytes, flush: true);
    }
    return (path: model.path, hash: hash);
  }
}
