import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:isolate';
import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';
import 'button_detector.dart';
import 'controller_model_runtime.dart';
import 'controller_builtin_model.dart';
import 'diagnostics.dart';

class _ObservationCancelled implements Exception {}

/// Only a paired controller owns this runtime; target capture never starts it.
class ControllerLocalVision extends ChangeNotifier {
  final LocalVisionSource _source;
  final ButtonInference Function() _runtimeFactory;
  final Future<Directory> Function() _cacheDirectory;
  ButtonInference? _runtime;
  ButtonModelManifest? _manifest;
  Future<void>? _prepareFuture;
  Object? _prepareOwner;
  Future<void> _retiring = Future<void>.value();
  bool _closed = false, _preparing = false, _ready = false, _observing = false;
  int _generation = 0;
  String _status = '控制手机本地模型待准备';
  String? _error, _lastFrame;
  double? _inferenceMs;
  int? _boxCount;
  ControllerLocalVision(LocalVisionSource source,
      {ButtonInference Function()? runtimeFactory,
      Future<Directory> Function()? cacheDirectory})
      : _source = source,
        _runtimeFactory = runtimeFactory ?? OrtButtonInference.new,
        _cacheDirectory = cacheDirectory ?? _defaultCache;
  static Future<Directory> _defaultCache() async => Directory(
      '${(await getApplicationCacheDirectory()).path}/controller-models');
  String get status => _status;
  String? get error => _error;
  bool get preparing => _preparing;
  bool get ready => _ready;
  double? get inferenceMs => _inferenceMs;
  int? get boxCount => _boxCount;
  void _emit() {
    if (!_closed) notifyListeners();
  }

  bool _valid(int generation) =>
      !_closed &&
      generation == _generation &&
      _source.isPaired &&
      _source.authorized;
  void _check(int generation) {
    if (!_valid(generation)) throw _ObservationCancelled();
  }

  static Future<String> _fileHash(String path) => Isolate.run(
      () => sha256.convert(File(path).readAsBytesSync()).toString());
  @override
  void dispose() {
    if (_closed) return;
    _closed = true;
    suspend();
    super.dispose();
  }

  Future<void> prepare() {
    if (_closed) return Future<void>.value();
    if (!_source.isPaired || !_source.authorized) {
      _status = '请在控制手机连接被控手机后准备模型';
      _emit();
      return Future<void>.value();
    }
    if (_ready) return Future<void>.value();
    if (_prepareFuture != null) return _prepareFuture!;
    final owner = Object();
    _prepareOwner = owner;
    final future = _prepare(_generation, owner);
    _prepareFuture = future;
    return future;
  }

  Future<void> _prepare(int generation, Object owner) async {
    ButtonInference? runtime;
    File? temporary;
    _preparing = true;
    _error = null;
    _status = '正在检查控制手机本地模型';
    _emit();
    try {
      await _retiring;
      _check(generation);
      // v47: 优先加载 APK 内置模型
      _status = '正在检查内置模型';
      _emit();
      try {
        final builtinPath = await BuiltinModelLoader.getModelPath();
        _check(generation);
        _status = '正在加载内置模型';
        _emit();
        final builtinRuntime = _runtimeFactory();
        await builtinRuntime.load(builtinPath, 'builtin');
        _runtime = builtinRuntime;
        runtime = builtinRuntime;
        _ready = true;
        _status = '内置模型已就绪';
        _emit();
        return;
      } catch (e) {
        if (identical(_runtime, runtime)) {}
        _status = '内置模型不可用，回退云端模型';
        _emit();
      }
      final obj = await _source.localVision('manifest', {});
      _check(generation);
      if (obj['available'] == false) {
        _status = '尚未配置控制手机本地模型';
        return;
      }
      final manifest = ButtonModelManifest.parse(obj);
      final directory = await _cacheDirectory();
      _check(generation);
      await directory.create(recursive: true);
      final file = File('${directory.path}/${manifest.sha256}.onnx');
      var cached = await file.exists();
      if (cached) {
        cached = await file.length() == manifest.size &&
            await _fileHash(file.path) == manifest.sha256;
      }
      _check(generation);
      if (!cached) {
        _status = '正在下载控制手机本地模型';
        _emit();
        final bytes = await _source.localModelBytes(manifest);
        _check(generation);
        if (bytes.length != manifest.size ||
            await Isolate.run(() => sha256.convert(bytes).toString()) !=
                manifest.sha256) {
          throw const FormatException('本地模型下载校验失败，未加载');
        }
        _check(generation);
        temporary = File(
            '${file.path}.$generation.${DateTime.now().microsecondsSinceEpoch}.part');
        await temporary.writeAsBytes(bytes, flush: true);
        _check(generation);
        await temporary.rename(file.path);
        temporary = null;
      }
      _status = '正在加载控制手机本地模型';
      _emit();
      runtime = _runtimeFactory();
      _runtime = runtime;
      await runtime.load(file.path, manifest.sha256);
      _check(generation);
      _manifest = manifest;
      _ready = true;
      _status = '模型已在控制手机就绪';
    } on _ObservationCancelled {
      if (runtime != null) {
        await runtime.close();
        if (identical(_runtime, runtime)) _runtime = null;
      }
    } catch (_) {
      if (runtime != null) {
        await runtime.close();
        if (identical(_runtime, runtime)) _runtime = null;
      }
      if (_valid(generation)) {
        _ready = false;
        _error = '本地模型准备失败，请检查网络或稍后重试。基础控制仍可使用。';
        _status = '控制手机本地模型未就绪';
      }
    } finally {
      if (temporary != null) {
        try {
          await temporary.delete();
        } catch (_) {}
      }
      if (identical(_prepareOwner, owner)) {
        _prepareOwner = null;
        _prepareFuture = null;
        _preparing = false;
        _emit();
      }
    }
  }

  Future<void> observe(String taskId, {bool Function()? isCurrent}) async {
    if (_closed ||
        _observing ||
        !_ready ||
        _runtime == null ||
        _manifest == null) {
      return;
    }
    final generation = _generation, runtime = _runtime!, manifest = _manifest!;
    bool current() =>
        _valid(generation) &&
        _ready &&
        identical(runtime, _runtime) &&
        (isCurrent?.call() ?? true);
    if (!current() || !RegExp(r'^[0-9a-f]{32}$').hasMatch(taskId)) return;
    _observing = true;
    try {
      final frame = await _source.localVision('frame', {'task_id': taskId});
      if (!current()) return;
      if (frame['state'] == 'waiting') {
        _status = '等待被控手机的新画面';
        _inferenceMs = null;
        _boxCount = null;
        _emit();
        return;
      }
      final id = frame['frame_id'],
          barrier = frame['barrier'],
          sequence = frame['sequence'],
          encoded = frame['jpegBase64'];
      final width = frame['width'], height = frame['height'];
      if (frame['task_id'] != taskId ||
          id is! String ||
          !RegExp(r'^[0-9a-f]{64}$').hasMatch(id) ||
          barrier is! String ||
          !RegExp(r'^[0-9a-f]{32}$').hasMatch(barrier) ||
          sequence is! int ||
          sequence < 1 ||
          width is! int ||
          height is! int ||
          width < 1 ||
          height < 1 ||
          width > 4096 ||
          height > 4096 ||
          encoded is! String ||
          encoded.length > 699052) {
        throw const FormatException('被控手机画面标识无效');
      }
      final key = '$taskId:$sequence:$id:$barrier';
      if (key == _lastFrame) return;
      final jpeg = base64Decode(encoded);
      if (jpeg.isEmpty ||
          jpeg.length > 524288 ||
          sha256.convert(jpeg).toString() != id) {
        throw const FormatException('被控手机画面校验失败');
      }
      if (!current()) return;
      final clock = Stopwatch()..start();
      final result = await runtime.infer(jpeg);
      if (!current() || clock.elapsedMilliseconds >= 2000) return;
      final ack = await _source.localVision('result', {
        'task_id': taskId,
        'frame_id': id,
        'barrier': barrier,
        'sequence': sequence,
        'model_sha256': manifest.sha256,
        'boxes': result.boxes.map((b) => b.toJson()).toList(),
        'inference_ms': result.inferenceMs
      });
      if (!current()) return;
      if (ack['accepted'] != true) throw const FormatException('本地识别结果未确认');
      _lastFrame = key;
      _inferenceMs = result.inferenceMs;
      _boxCount = result.boxes.length;
      _status = '控制手机正在本机识别被控画面';
      _error = null;
      _emit();
    } on ControlHttpFailure catch (e) {
      if (current() && e.status != 409) {
        _error = '本地识别连接已失效，请重新连接被控手机。';
        _status = '本地识别已暂停';
        suspend();
      }
    } catch (_) {
      if (current()) {
        _error = '本机识别未完成，已暂停；可重试模型准备。';
        _status = '本地识别已暂停';
        suspend();
      }
    } finally {
      _observing = false;
    }
  }

  void suspend() {
    _generation++;
    _ready = false;
    _preparing = false;
    _prepareFuture = null;
    _prepareOwner = null;
    _manifest = null;
    _lastFrame = null;
    _inferenceMs = null;
    _boxCount = null;
    _status = '控制手机本地识别已暂停';
    final runtime = _runtime;
    _runtime = null;
    if (runtime != null) {
      final previous = _retiring;
      _retiring = () async {
        await previous;
        await runtime.close();
      }();
    }
    _emit();
  }

  Future<void> close() async {
    dispose();
    await _retiring;
  }
}
