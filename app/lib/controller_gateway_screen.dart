import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'ble_ota_service.dart';
import 'control_client.dart';
import 'control_screen.dart';
import 'product_widgets.dart';
import 'product_settings.dart';

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
      if (mounted) setState(() => _error = '手机中转未连接：$e。请先在原中转手机释放蓝牙连接，再重试。');
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
        appBar: AppBar(title: const Text('手机蓝牙中转'), actions: [
          IconButton(
              tooltip: '设置与诊断',
              icon: const Icon(Icons.settings_outlined),
              onPressed: _busy
                  ? null
                  : () => Navigator.of(context).push(MaterialPageRoute<void>(
                      builder: (_) =>
                          ProductSettingsScreen(diagnostic: _error))))
        ]),
        body: ListView(padding: const EdgeInsets.all(24), children: [
          const Text('此手机通过网络中转板端任务，无需连接 USB 或共享本机屏幕。被控手机仍须通过 USB 共享画面。'),
          const SizedBox(height: 12),
          const Text(
              '控制板同一时刻只连接一台中转手机。请先在原手机停止操作并释放连接，再连接本机。连接后仍会检查云端状态；返回此页会释放本机中转，旧操作不会重放。'),
          const SizedBox(height: 16),
          FilledButton(
              onPressed: _busy ? null : _search,
              child: Text(_busy ? '正在连接手机中转…' : '原连接已释放，扫描控制板')),
          if (_error != null)
            ProductError(_error!.contains('固件')
                ? _error!
                : '手机中转尚未连接。请确认原手机已释放蓝牙，检查本机蓝牙和网络后重试。'),
          for (final result in _devices.values)
            Card(
                child: ListTile(
                    title: Text(result.device.platformName.isEmpty
                        ? 'PhoneCtl 控制板'
                        : result.device.platformName),
                    subtitle: const Text('选择此控制板进行连接'),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: _busy ? null : () => _connect(result))),
        ]),
      );
}
