import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

/// The opt-in and the actual Android service connection are independent states.
class AccessibilityAssistCard extends StatefulWidget {
  const AccessibilityAssistCard({super.key});
  @override
  State<AccessibilityAssistCard> createState() =>
      _AccessibilityAssistCardState();
}

class _AccessibilityAssistCardState extends State<AccessibilityAssistCard> {
  static const _channel = MethodChannel('pcflash/accessibility');
  Timer? _timer;
  bool _enabled = false,
      _connected = false,
      _capture = false,
      _busy = false,
      _reading = false;
  String? _error;
  int _generation = 0;
  @override
  void initState() {
    super.initState();
    if (defaultTargetPlatform != TargetPlatform.android) return;
    _read();
    _timer = Timer.periodic(const Duration(seconds: 2), (_) => _read());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  void _update(Map<String, dynamic>? value) {
    if (!mounted) return;
    if (value == null) throw const FormatException('状态不可读');
    setState(() {
      _enabled = value['enabled'] == true;
      _connected = value['connected'] == true;
      _capture = value['captureActive'] == true;
      _error = null;
    });
  }

  Future<void> _read() async {
    if (_reading || _busy) return;
    _reading = true;
    final generation = _generation;
    try {
      final value = await _channel.invokeMapMethod<String, dynamic>('status');
      if (generation == _generation && !_busy) _update(value);
    } catch (_) {
      if (mounted && generation == _generation && !_busy) {
        setState(() => _error = '暂时无法读取辅助状态，请稍后重试');
      }
    } finally {
      _reading = false;
    }
  }

  Future<void> _toggle(bool enabled) async {
    if (_busy) return;
    _generation++;
    setState(() => _busy = true);
    try {
      _update(await _channel.invokeMapMethod<String, dynamic>(
          'setEnabled', {'enabled': enabled}));
    } catch (_) {
      if (mounted) setState(() => _error = '辅助设置未保存，请重试');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _settings() async {
    try {
      await _channel.invokeMethod<void>('openSettings');
    } catch (_) {
      if (mounted) setState(() => _error = '无法打开系统设置，请从系统的无障碍设置进入');
    }
  }

  @override
  Widget build(BuildContext context) {
    if (defaultTargetPlatform != TargetPlatform.android) {
      return const SizedBox.shrink();
    }
    final status = !_enabled
        ? '已关闭'
        : !_connected
            ? '等待系统开启'
            : !_capture
                ? '已连接，等待屏幕共享'
                : '已连接，共享任务中可辅助定位';
    return Card(
        child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              SwitchListTile(
                  title: const Text('无障碍辅助定位'),
                  subtitle: Text(status),
                  value: _enabled,
                  onChanged: _busy ? null : _toggle),
              const Padding(
                  padding: EdgeInsets.symmetric(horizontal: 16),
                  child: Text(
                      '读取账单应用和桌面的可见文字及控件位置，随当前共享画面上传，帮助更快定位。操作结果仍以新画面核验。可随时关闭。')),
              if (_enabled && !_connected)
                Padding(
                    padding: const EdgeInsets.all(12),
                    child: TextButton.icon(
                        onPressed: _settings,
                        icon: const Icon(Icons.accessibility_new),
                        label: const Text('前往系统设置'))),
              if (_error != null)
                Padding(
                    padding: const EdgeInsets.all(16),
                    child: Text(_error!,
                        style: TextStyle(
                            color: Theme.of(context).colorScheme.error))),
            ])));
  }
}
