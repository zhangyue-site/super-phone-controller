import 'dart:async';
import 'package:flutter/material.dart';
import 'screen_share.dart';
import 'usb_launch.dart';

/// Phone B: USB identity and human-consented whole-screen capture only.
class UsbTargetScreen extends StatefulWidget {
  final UsbAttachment attachment;
  final bool Function() isCurrent;
  const UsbTargetScreen(
      {super.key, required this.attachment, required this.isCurrent});
  @override
  State<UsbTargetScreen> createState() => _UsbTargetScreenState();
}

class _UsbTargetScreenState extends State<UsbTargetScreen> {
  Timer? _timer;
  bool _busy = false, _active = false, _polling = false;
  bool _pointerReady = false;
  int _generation = 0;
  String _status = '准备请求共享整个屏幕';
  String? _error;
  bool _current(int generation) =>
      mounted && widget.isCurrent() && generation == _generation;
  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(seconds: 2), (_) => _poll());
    WidgetsBinding.instance.addPostFrameCallback((_) => _start());
  }

  Future<void> _poll() async {
    if (_polling || !mounted) return;
    if (!widget.isCurrent()) {
      _generation++;
      setState(() {
        _active = false;
        _status = 'USB连接已改变，请重新插入控制板';
      });
      return;
    }
    final generation = _generation;
    _polling = true;
    try {
      final status = await ScreenShare.status();
      if (_current(generation)) {
        setState(() {
          _status = status.capture;
          _pointerReady = status.pointerReady;
        });
      }
      final active = await ScreenShare.isActive();
      if (_current(generation)) setState(() => _active = active);
    } catch (_) {/* A later poll can recover the status. */} finally {
      _polling = false;
    }
  }

  Future<void> _start() async {
    if (_busy || !widget.isCurrent()) return;
    final generation = ++_generation;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final active = await ScreenShare.isActive();
      if (!_current(generation)) return;
      if (!active) {
        await ScreenShare.startUsb(widget.attachment,
            isCurrent: () => _current(generation));
      }
      if (_current(generation)) {
        setState(() {
          _active = true;
          _status = '正在共享整个屏幕';
        });
      }
    } catch (e) {
      if (_current(generation)) setState(() => _error = '未开始共享：$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _stop() async {
    _generation++;
    try {
      await ScreenShare.stop();
    } finally {
      if (mounted) {
        setState(() {
          _active = false;
          _status = '已停止共享';
        });
      }
    }
  }

  @override
  void dispose() {
    _generation++;
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('被控手机 · 屏幕共享')),
        body: ListView(padding: const EdgeInsets.all(24), children: [
          const Icon(Icons.usb, size: 48),
          const SizedBox(height: 16),
          const Text('已识别USB控制板', style: TextStyle(fontSize: 22)),
          Text('USB序列号：${widget.attachment.serial}'),
          const SizedBox(height: 20),
          const Text('请在系统对话框中同意共享整个屏幕。画面将上传云端供AI分析。'),
          const SizedBox(height: 12),
          const Text('手机操作由控制板通过USB HID执行，请保持控制板连接。'),
          const SizedBox(height: 20),
          Text(_status),
          Text(_pointerReady ? 'HID控制板：已就绪' : 'HID控制板：等待板端许可'),
          if (_error != null) Text(_error!),
          const SizedBox(height: 16),
          FilledButton(
              onPressed:
                  _busy || _active || !widget.isCurrent() ? null : _start,
              child: Text(_busy ? '正在请求系统授权…' : '重试共享整个屏幕')),
          TextButton(onPressed: _stop, child: const Text('停止共享')),
        ]),
      );
}
