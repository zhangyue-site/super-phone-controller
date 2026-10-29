import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'ble_ota_service.dart';
import 'control_client.dart';
import 'control_screen.dart';

/// Explicit possession of the board's single BLE link; never starts capture.
class ControllerGatewayScreen extends StatefulWidget {
  const ControllerGatewayScreen({super.key});
  @override
  State<ControllerGatewayScreen> createState() =>
      _ControllerGatewayScreenState();
}

class _ControllerGatewayScreenState extends State<ControllerGatewayScreen> {
  final _service = BleOtaService();
  StreamSubscription<List<ScanResult>>? _scan;
  final Map<String, ScanResult> _devices = {};
  bool _busy = false;
  String? _error;
  ControlClient? _client;

  Future<void> _search() async {
    if (_busy) return;
    setState(() {
      _error = null;
      _devices.clear();
    });
    _scan ??= _service.scanResults.listen((results) {
      if (!mounted) return;
      setState(() {
        for (final result in results) {
          _devices[result.device.remoteId.str] = result;
        }
      });
    });
    try {
      await _service.startScan();
    } catch (e) {
      if (mounted) setState(() => _error = '扫描失败：$e');
    }
  }

  Future<void> _connect(ScanResult result) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    final client = ControlClient();
    _client = client;
    try {
      await _service.stopScan();
      await _service.connect(result.device);
      if (!_service.supportsLocalControl) {
        throw StateError('此固件尚不支持应用中转，请先升级控制板');
      }
      await client.authorize(_service);
      if (!mounted) return;
      await Navigator.of(context).push(MaterialPageRoute<void>(
          builder: (_) => ControlScreen(service: _service, client: client)));
    } catch (e) {
      if (mounted) setState(() => _error = '网关未建立：$e。请先在原网关手机释放蓝牙连接，再重试。');
    } finally {
      await client.shutdown();
      await _service.disconnect();
      _client = null;
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  void dispose() {
    _scan?.cancel();
    _service.stopScan();
    _client?.close();
    _service.disconnect();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('此手机作为蓝牙网关')),
        body: ListView(padding: const EdgeInsets.all(24), children: [
          const Text('此手机通过网络中转板端任务，无需连接 USB 或共享本机屏幕。被控手机仍须通过 USB 共享画面。'),
          const SizedBox(height: 12),
          const Text(
              '控制板只允许一个蓝牙网关。请先在原网关手机退出控制并断开蓝牙，再连接本机；连接成功后仍需云端握手，不能以蓝牙连接判断云在线。返回此页会释放本机网关，旧动作不会重发。'),
          const SizedBox(height: 16),
          FilledButton(
              onPressed: _busy ? null : _search,
              child: Text(_busy ? '正在建立网关…' : '原网关已释放，扫描控制板')),
          if (_error != null)
            Semantics(
                liveRegion: true,
                child: Text(_error!,
                    style:
                        TextStyle(color: Theme.of(context).colorScheme.error))),
          for (final result in _devices.values)
            Card(
                child: ListTile(
                    title: Text(result.device.platformName.isEmpty
                        ? 'PhoneCtl 控制板'
                        : result.device.platformName),
                    subtitle: Text(result.device.remoteId.str),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: _busy ? null : () => _connect(result))),
        ]),
      );
}
