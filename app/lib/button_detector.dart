import 'dart:math' as math;
import 'dart:typed_data';
import 'package:image/image.dart' as image;

class ButtonModelManifest {
  final String version, sha256;
  final int size;
  const ButtonModelManifest(this.version, this.sha256, this.size);
  static ButtonModelManifest parse(Map<String, dynamic> obj) {
    final version = obj['version'], sha = obj['sha256'], size = obj['size'];
    if (obj['available'] != true ||
        obj['format'] != 'onnx' ||
        version is! String ||
        version.isEmpty ||
        version.length > 128 ||
        sha is! String ||
        !RegExp(r'^[0-9a-f]{64}$').hasMatch(sha) ||
        size is! int ||
        size < 1 ||
        size > 32 * 1024 * 1024 ||
        obj['inputWidth'] != 320 ||
        obj['inputHeight'] != 320 ||
        obj['outputLayout'] != 'xywh-score' ||
        obj['preprocess'] != 'stretch-rgb-0-1') {
      throw const FormatException('本地模型描述无效或不兼容');
    }
    return ButtonModelManifest(version, sha, size);
  }
}

class ButtonBox {
  final double x, y, width, height, score;
  const ButtonBox(this.x, this.y, this.width, this.height, this.score);
  Map<String, double> toJson() =>
      {'x': x, 'y': y, 'width': width, 'height': height, 'score': score};
  static ButtonBox parse(Map<dynamic, dynamic> obj) {
    final values = [
      obj['x'],
      obj['y'],
      obj['width'],
      obj['height'],
      obj['score']
    ];
    if (values.any((v) => v is! num || !v.isFinite || v < 0 || v > 1)) {
      throw const FormatException('按钮检测结果无效');
    }
    final b = ButtonBox.fromValues(values.cast<num>());
    if (b.width <= 0 ||
        b.height <= 0 ||
        b.x + b.width > 1.000001 ||
        b.y + b.height > 1.000001) {
      throw const FormatException('按钮检测坐标越界');
    }
    return b;
  }

  factory ButtonBox.fromValues(List<num> v) => ButtonBox(v[0].toDouble(),
      v[1].toDouble(), v[2].toDouble(), v[3].toDouble(), v[4].toDouble());
}

/// Exact single-class YOLO output; geometry is observation, never click permission.
List<ButtonBox> decodeButtonOutput(Object? value) {
  if (value is! List || value.length != 1 || value[0] is! List) {
    throw const FormatException('按钮模型输出形状不兼容');
  }
  final rows = value[0] as List;
  if (rows.length != 5 || rows.any((r) => r is! List || r.length != 2100)) {
    throw const FormatException('按钮模型输出形状不兼容');
  }
  double number(int r, int i) {
    final n = (rows[r] as List)[i];
    if (n is! num || !n.isFinite) throw const FormatException('按钮模型包含无效数字');
    return n.toDouble();
  }

  final candidates = <ButtonBox>[];
  for (var i = 0; i < 2100; i++) {
    final cx = number(0, i),
        cy = number(1, i),
        w = number(2, i),
        h = number(3, i),
        score = number(4, i);
    if (score < 0 || score > 1) throw const FormatException('按钮模型置信度无效');
    if (score < .45 || w <= 0 || h <= 0) continue;
    final left = ((cx - w / 2) / 320).clamp(0.0, 1.0),
        top = ((cy - h / 2) / 320).clamp(0.0, 1.0);
    final right = ((cx + w / 2) / 320).clamp(0.0, 1.0),
        bottom = ((cy + h / 2) / 320).clamp(0.0, 1.0);
    if (right <= left || bottom <= top) continue;
    candidates.add(ButtonBox(left, top, right - left, bottom - top, score));
  }
  candidates.sort((a, b) => b.score.compareTo(a.score));
  final kept = <ButtonBox>[];
  for (final b in candidates) {
    var overlaps = false;
    for (final a in kept) {
      final w = math.max(
          0.0, math.min(a.x + a.width, b.x + b.width) - math.max(a.x, b.x));
      final h = math.max(
          0.0, math.min(a.y + a.height, b.y + b.height) - math.max(a.y, b.y));
      final intersection = w * h,
          union = a.width * a.height + b.width * b.height - intersection;
      if (union > 0 && intersection / union > .45) {
        overlaps = true;
        break;
      }
    }
    if (!overlaps) kept.add(b);
    if (kept.length == 100) break;
  }
  return kept;
}

/// Bounds are checked from JPEG headers before pixel allocation.
Float32List preprocessButtonJpeg(Uint8List jpeg) {
  if (jpeg.isEmpty || jpeg.length > 524288) {
    throw const FormatException('共享帧大小无效');
  }
  try {
    final decoder = image.JpegDecoder();
    final info = decoder.startDecode(jpeg);
    if (info == null ||
        info.width < 1 ||
        info.height < 1 ||
        info.width > 4096 ||
        info.height > 4096 ||
        info.width * info.height > 8388608) {
      throw const FormatException('共享画面尺寸无效');
    }
    final original = decoder.decodeFrame(0);
    if (original == null) throw const FormatException('共享画面无法读取');
    final small = image.copyResize(original,
        width: 320, height: 320, interpolation: image.Interpolation.linear);
    final data = Float32List(3 * 320 * 320);
    for (var y = 0; y < 320; y++) {
      for (var x = 0; x < 320; x++) {
        final p = small.getPixel(x, y);
        final i = y * 320 + x;
        data[i] = p.r / 255;
        data[320 * 320 + i] = p.g / 255;
        data[2 * 320 * 320 + i] = p.b / 255;
      }
    }
    return data;
  } on FormatException {
    rethrow;
  } catch (_) {
    throw const FormatException('共享画面无法读取');
  }
}

abstract interface class LocalVisionSource {
  bool get isPaired;
  bool get authorized;
  Future<Map<String, dynamic>> localVision(
      String operation, Map<String, dynamic> body);
  Future<Uint8List> localModelBytes(ButtonModelManifest manifest);
}
