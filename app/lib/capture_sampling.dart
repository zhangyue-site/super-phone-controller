import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

class CaptureSamplingCard extends StatefulWidget {
  const CaptureSamplingCard({super.key});
  @override
  State<CaptureSamplingCard> createState() => _CaptureSamplingCardState();
}

class _CaptureSamplingCardState extends State<CaptureSamplingCard> {
  static const _channel = MethodChannel('pcflash/capture-sampling');
  bool _enabled = false, _busy = true;
  String? _error;
  @override
  void initState() {
    super.initState();
    if (defaultTargetPlatform == TargetPlatform.android) {
      _read();
    }
  }

  bool _value(Map<String, dynamic>? value) {
    if (value == null || value['enabled'] is! bool) {
      throw const FormatException();
    }
    return value['enabled'] as bool;
  }

  Future<void> _read() async {
    try {
      final value =
          _value(await _channel.invokeMapMethod<String, dynamic>('status'));
      if (mounted) setState(() => _enabled = value);
    } catch (_) {
      if (mounted) setState(() => _error = '暂时无法读取取样设置');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _toggle(bool enabled) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      final value = _value(await _channel.invokeMapMethod<String, dynamic>(
          'setEnabled', {'enabled': enabled}));
      if (mounted) {
        setState(() {
          _enabled = value;
          _error = null;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _error = '取样设置未保存，请重试');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (defaultTargetPlatform != TargetPlatform.android) {
      return const SizedBox.shrink();
    }
    return Card(
        child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              SwitchListTile(
                  title: const Text('静态页面持续取样（实验）'),
                  subtitle: Text(_busy
                      ? '正在读取或保存设置'
                      : _enabled
                          ? '已开启，仅在任务等待新画面时取样'
                          : '已关闭'),
                  value: _enabled,
                  onChanged: _busy ? null : _toggle),
              const Padding(
                  padding: EdgeInsets.symmetric(horizontal: 16),
                  child: Text('页面静止且任务等不到新画面时尝试继续取样，可能增加耗电。只在屏幕共享期间生效，可随时关闭。')),
              if (_error != null)
                Padding(
                    padding: const EdgeInsets.all(16),
                    child: Text(_error!,
                        style: TextStyle(
                            color: Theme.of(context).colorScheme.error))),
            ])));
  }
}
