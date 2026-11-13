import 'dart:convert';
import 'dart:typed_data';
import 'dart:ui' as ui;
import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'button_detector.dart';

/// An explicit, ephemeral observation; never a saved result or success signal.
class TaskFramePreview extends StatefulWidget {
  const TaskFramePreview(
      {super.key,
      required this.source,
      required this.taskId,
      required this.sourceLabel,
      this.active = true,
      this.isCurrent});
  final LocalVisionSource source;
  final String taskId, sourceLabel;
  final bool active;
  final bool Function()? isCurrent;
  @override
  State<TaskFramePreview> createState() => _TaskFramePreviewState();
}

class _TaskFramePreviewState extends State<TaskFramePreview> {
  Uint8List? _jpeg;
  String? _error;
  bool _busy = false;
  int _generation = 0;
  bool _current(int generation) =>
      mounted &&
      generation == _generation &&
      widget.active &&
      widget.source.isPaired &&
      widget.source.authorized &&
      (widget.isCurrent?.call() ?? true);

  @override
  void didUpdateWidget(covariant TaskFramePreview oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.taskId != widget.taskId ||
        !identical(oldWidget.source, widget.source) ||
        !widget.active) {
      _generation++;
      _jpeg = null;
      _error = null;
      _busy = false;
    }
  }

  void _close() => setState(() {
        _generation++;
        _jpeg = null;
        _error = null;
        _busy = false;
      });

  Future<void> _fetch() async {
    if (_busy || !widget.active) return;
    final generation = ++_generation;
    final taskId = widget.taskId;
    setState(() {
      _busy = true;
      _jpeg = null;
      _error = null;
    });
    try {
      if (!_current(generation) ||
          !RegExp(r'^[0-9a-f]{32}$').hasMatch(taskId)) {
        throw const FormatException();
      }
      final frame =
          await widget.source.localVision('frame', {'task_id': taskId});
      if (!_current(generation)) return;
      if (frame['task_id'] != taskId) throw const FormatException();
      if (frame['state'] == 'waiting') {
        setState(() => _error = '等待被控手机的新画面，请稍后重试。');
        return;
      }
      final id = frame['frame_id'], barrier = frame['barrier'];
      final sequence = frame['sequence'],
          width = frame['width'],
          height = frame['height'];
      final encoded = frame['jpegBase64'];
      if (id is! String ||
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
        throw const FormatException();
      }
      final bytes = base64Decode(encoded);
      if (bytes.length < 4 ||
          bytes.length > 524288 ||
          bytes[0] != 0xff ||
          bytes[1] != 0xd8 ||
          sha256.convert(bytes).toString() != id) {
        throw const FormatException();
      }
      final buffer = await ui.ImmutableBuffer.fromUint8List(bytes);
      try {
        final descriptor = await ui.ImageDescriptor.encoded(buffer);
        try {
          if (descriptor.width != width || descriptor.height != height) {
            throw const FormatException();
          }
        } finally {
          descriptor.dispose();
        }
      } finally {
        buffer.dispose();
      }
      if (_current(generation)) setState(() => _jpeg = bytes);
    } catch (_) {
      if (_current(generation)) {
        setState(() => _error = '未能显示当前画面。请确认任务仍在执行、共享有效后重试。');
      }
    } finally {
      if (mounted && generation == _generation) setState(() => _busy = false);
    }
  }

  @override
  void dispose() {
    _generation++;
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.active) return const SizedBox.shrink();
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      OutlinedButton.icon(
          onPressed: _busy ? null : _fetch,
          icon: const Icon(Icons.image_outlined),
          label: Text(_busy
              ? '正在获取当前画面…'
              : _jpeg == null
                  ? '查看当前画面'
                  : '刷新当前画面')),
      if (_busy || _jpeg != null || _error != null)
        Align(
            alignment: Alignment.centerRight,
            child: IconButton(
                tooltip: '关闭当前画面',
                onPressed: _close,
                icon: const Icon(Icons.close))),
      if (_error != null)
        Semantics(
            liveRegion: true,
            child: Text(_error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error))),
      if (_jpeg != null) ...[
        Text('来源：${widget.sourceLabel} · 本次按需获取，不实时更新'),
        const Text('当前观察画面，不是最终核验证据'),
        const SizedBox(height: 8),
        Image.memory(_jpeg!,
            gaplessPlayback: false,
            fit: BoxFit.contain,
            height: 300,
            semanticLabel: '${widget.sourceLabel}当前任务的观察画面',
            errorBuilder: (context, error, stackTrace) =>
                const Text('画面无法解码，请关闭后重新获取。')),
      ],
    ]);
  }
}
