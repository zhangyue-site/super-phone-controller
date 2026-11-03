// local_vision_client.dart — 端侧小模型推理客户端（ZY-Button-v5）
//
// 协议（服务端 display_service/local_vision.py 已实现）：
//   POST /app-local-vision/manifest  {}                      -> 模型清单
//   POST /app-local-vision/model     {"sha256": "..."}       -> 模型字节
//   POST /app-local-vision/frame     {"task_id": "..."}      -> {frame_id, barrier, sequence, jpegBase64}
//   POST /app-local-vision/result    {task_id, frame_id, barrier, sequence, model_sha256, boxes[], inference_ms}
//
// 约定：box 为归一化 {x, y, width, height, score}，左上角原点；模型输入 320x320，
// 预处理 stretch-rgb-0-1（直接拉伸、除以 255，不做 letterbox），输出布局 xywh-score。
//
// 依赖：flutter pub add onnxruntime image
//   onnxruntime: ^1.4.1   （Flutter 端 ONNX Runtime，iOS/Android 均支持）
//   image: ^4.2.0          （纯 Dart 解码/缩放，避免平台差异）
//
// 用法（在屏幕任务流程中）：
//   final lv = LocalVisionClient(baseUrl, token);
//   final model = await lv.ensureModel();          // 首次下载缓存
//   final frame = await lv.requestFrame(taskId);
//   final boxes = await lv.infer(frame, model);    // 端侧推理，约 10-30ms
//   await lv.submit(taskId, frame, model, boxes);  // 回传几何提示

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:http/http.dart' as http;
import 'package:image/image.dart' as img;
import 'package:onnxruntime/onnxruntime.dart';
import 'package:path_provider/path_provider.dart';

class LocalVisionModel {
  LocalVisionModel(this.version, this.sha256, this.path, this.size);
  final String version;
  final String sha256;
  final String path;
  final int size;
}

class LocalVisionFrame {
  LocalVisionFrame(this.taskId, this.frameId, this.barrier, this.sequence, this.jpegBytes);
  final String taskId;
  final String frameId;
  final String barrier;
  final int sequence;
  final Uint8List jpegBytes;
}

class LocalVisionClient {
  LocalVisionClient(this.baseUrl, this.bearer);
  final String baseUrl;
  final String bearer;

  OrtSession? _session;
  String? _sessionSha;

  Map<String, String> get _headers => {
        'Authorization': 'Bearer $bearer',
        'Content-Type': 'application/json',
      };

  Future<Map<String, dynamic>> _post(String path, Map<String, dynamic> body) async {
    final r = await http
        .post(Uri.parse('$baseUrl$path'), headers: _headers, body: jsonEncode(body))
        .timeout(const Duration(seconds: 20));
    if (r.statusCode != 200) {
      throw HttpException('local-vision $path ${r.statusCode}: ${r.body}');
    }
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  /// 拉取/校验模型（sha 变化才重新下载）
  Future<LocalVisionModel> ensureModel() async {
    final manifest = await _post('/app-local-vision/manifest', {});
    if (manifest['available'] != true) throw StateError('model unavailable');
    final sha = manifest['sha256'] as String;
    final version = manifest['version'] as String;
    final dir = await getApplicationSupportDirectory();
    final file = File('${dir.path}/local_vision_$sha.onnx');
    if (!await file.exists() || await file.length() != manifest['size']) {
      final r = await http
          .post(Uri.parse('$baseUrl/app-local-vision/model'),
              headers: _headers, body: jsonEncode({'sha256': sha}))
          .timeout(const Duration(minutes: 2));
      if (r.statusCode != 200) throw HttpException('model download ${r.statusCode}');
      await file.writeAsBytes(r.bodyBytes, flush: true);
    }
    return LocalVisionModel(version, sha, file.path, manifest['size'] as int);
  }

  Future<LocalVisionFrame> requestFrame(String taskId) async {
    final r = await _post('/app-local-vision/frame', {'task_id': taskId});
    if (r['state'] == 'waiting') throw StateError('frame not ready');
    return LocalVisionFrame(
      taskId,
      r['frame_id'] as String,
      r['barrier'] as String,
      r['sequence'] as int,
      base64Decode(r['jpegBase64'] as String),
    );
  }

  /// 端侧推理：JPEG -> 320x320 float32 CHW -> ONNX -> NMS -> 归一化框
  Future<List<Map<String, double>>> infer(LocalVisionFrame frame, LocalVisionModel model,
      {double conf = 0.45, double iou = 0.45}) async {
    if (_session == null || _sessionSha != model.sha256) {
      _session?.release();
      _session = await OrtSession.fromFile(File(model.path));
      _sessionSha = model.sha256;
    }
    final decoded = img.decodeJpg(frame.jpegBytes);
    if (decoded == null) throw const FormatException('bad jpeg');
    final W = decoded.width, H = decoded.height;
    final resized = img.copyResize(decoded, width: 320, height: 320);
    final input = Float32List(1 * 3 * 320 * 320);
    var i = 0;
    for (var c = 0; c < 3; c++) {
      for (var y = 0; y < 320; y++) {
        for (var x = 0; x < 320; x++) {
          final p = resized.getPixel(x, y);
          final v = c == 0 ? p.r : (c == 1 ? p.g : p.b);
          input[i++] = v / 255.0;
        }
      }
    }
    final tensor = OrtValueTensor.createTensorWithDataList(input, [1, 3, 320, 320]);
    final outputs = await _session!.run(OrtRunOptions(), {'images': tensor});
    tensor.release();
    // 输出 (1,5,2100) 或 (1,2100,5) —— 统一成 N×5(xywh+score)
    final raw = outputs.first!.value as List;
    outputs.forEach((o) => o?.release());
    final first = raw.first as List; // [5][N] 或 [N][5]
    final rows = <List<double>>[];
    if ((first.length == 5 || first.length == 6) && first.first is List) {
      final ch = first.length;
      final n = (first.first as List).length;
      for (var k = 0; k < n; k++) {
        rows.add([for (var c = 0; c < ch; c++) ((first[c] as List)[k] as num).toDouble()]);
      }
    } else {
      for (final row in first) {
        rows.add([for (final v in (row as List)) (v as num).toDouble()]);
      }
    }
    final boxes = _nms(rows, conf, iou);
    return [
      for (final b in boxes)
        {
          'x': b[0] / 320, 'y': b[1] / 320,
          'width': (b[2] - b[0]) / 320, 'height': (b[3] - b[1]) / 320,
          'score': b[4],
        }
    ].where((b) => (b['width']! > 0) && (b['height']! > 0)).toList();
  }

  static List<List<double>> _nms(List<List<double>> rows, double conf, double iouThres) {
    final cand = rows.where((r) => r[4] >= conf).toList()
      ..sort((a, b) => b[4].compareTo(a[4]));
    final keep = <List<double>>[];
    for (final c in cand) {
      var ok = true;
      for (final k in keep) {
        final ix = (c[0] - c[2] / 2 < k[2] && k[0] - k[2] / 2 < c[0] + c[2] / 2);
        // 简化：用中心点+宽高做 IoU
        final ax1 = c[0] - c[2] / 2, ay1 = c[1] - c[3] / 2, ax2 = c[0] + c[2] / 2, ay2 = c[1] + c[3] / 2;
        final bx1 = k[0] - k[2] / 2, by1 = k[1] - k[3] / 2, bx2 = k[0] + k[2] / 2, by2 = k[1] + k[3] / 2;
        final iw = (ax2 < bx2 ? ax2 : bx2) - (ax1 > bx1 ? ax1 : bx1);
        final ih = (ay2 < by2 ? ay2 : by2) - (ay1 > by1 ? ay1 : by1);
        final inter = (iw > 0 ? iw : 0) * (ih > 0 ? ih : 0);
        final uni = c[2] * c[3] + k[2] * k[3] - inter;
        if (inter / uni > iouThres) {
          ok = false;
          break;
        }
        if (!ix) continue;
      }
      if (ok) keep.add(c);
    }
    return keep;
  }

  /// 回传几何提示（服务端只接受与模型 sha 一致的帧结果）
  Future<void> submit(String taskId, LocalVisionFrame frame, LocalVisionModel model,
      List<Map<String, double>> boxes, int inferenceMs) async {
    await _post('/app-local-vision/result', {
      'task_id': taskId,
      'frame_id': frame.frameId,
      'barrier': frame.barrier,
      'sequence': frame.sequence,
      'model_sha256': model.sha256,
      'boxes': boxes,
      'inference_ms': inferenceMs,
    });
  }
}
