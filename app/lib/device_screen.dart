import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';

import 'ble_ota_service.dart';
import 'firmware_screen.dart';
import 'theme.dart';
import 'widgets.dart';

/// 屏幕 1：扫描并选择要刷的板子。
///
/// 设计取舍：不显示"连接中"这种阻塞态——BLE 扫描本身是流式的，用户要的是
/// 立刻看到板子出现。所以扫描一进来就启动，列表随发现增长。
class DeviceScreen extends StatefulWidget {
  const DeviceScreen({super.key});

  @override
  State<DeviceScreen> createState() => _DeviceScreenState();
}

class _DeviceScreenState extends State<DeviceScreen> {
  final _svc = BleOtaService();
  StreamSubscription? _scanSub;
  final Map<String, ScanResult> _found = {};
  bool _scanning = false;
  String? _error;
  Timer? _autoStop;

  @override
  void initState() {
    super.initState();
    _checkBluetooth();
  }

  Future<void> _checkBluetooth() async {
    if (!await FlutterBluePlus.isSupported) {
      setState(() => _error = '这台设备不支持蓝牙');
      return;
    }
    final state = await FlutterBluePlus.adapterState.first;
    if (state != BluetoothAdapterState.on) {
      setState(() => _error = '蓝牙未开启，请先在系统设置里打开');
      return;
    }
    _startScan();
  }

  Future<void> _startScan() async {
    if (_scanning) return;
    setState(() {
      _scanning = true;
      _error = null;
      _found.clear();
    });

    _scanSub = _svc.scan().listen((results) {
      if (!mounted) return;
      setState(() {
        for (final r in results) {
          _found[r.device.remoteId.str] = r;
        }
      });
    });

    // 8 秒没动静就停，省电；用户可手动重新扫。
    _autoStop?.cancel();
    _autoStop = Timer(const Duration(seconds: 8), _stopScan);
  }

  Future<void> _stopScan() async {
    _autoStop?.cancel();
    await _svc.stopScan();
    if (!mounted) return;
    setState(() => _scanning = false);
  }

  @override
  void dispose() {
    _autoStop?.cancel();
    _scanSub?.cancel();
    _svc.disconnect();
    super.dispose();
  }

  List<ScanResult> get _sorted {
    final list = _found.values.toList()
      ..sort((a, b) => b.rssi.compareTo(a.rssi));
    return list;
  }

  Future<void> _open(ScanResult r) async {
    await _stopScan();
    if (!mounted) return;
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => FirmwareScreen(service: _svc, device: r.device),
    ));
    // 从推送页返回后重新扫，避免板子重启后列表是旧的。
    if (mounted) _startScan();
  }

  @override
  Widget build(BuildContext context) {
    final devices = _sorted;
    return Scaffold(
      appBar: AppBar(
        title: const Text('PhoneCtl Flash'),
        actions: [
          IconButton(
            tooltip: '重新扫描',
            onPressed: _scanning ? null : _checkBluetooth,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: Column(
        children: [
          _ScanBar(scanning: _scanning, count: devices.length, onToggle: () {
            _scanning ? _stopScan() : _startScan();
          }),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
              child: InfoBanner(
                icon: Icons.bluetooth_disabled,
                color: AppTheme.danger,
                text: _error!,
              ),
            ),
          Expanded(
            child: devices.isEmpty
                ? _EmptyState(scanning: _scanning)
                : ListView.separated(
                    padding: const EdgeInsets.all(16),
                    itemCount: devices.length,
                    separatorBuilder: (_, __) => const SizedBox(height: 10),
                    itemBuilder: (_, i) =>
                        _DeviceCard(result: devices[i], onTap: () => _open(devices[i])),
                  ),
          ),
        ],
      ),
    );
  }
}

class _ScanBar extends StatelessWidget {
  final bool scanning;
  final int count;
  final VoidCallback onToggle;

  const _ScanBar({
    required this.scanning,
    required this.count,
    required this.onToggle,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 12),
      child: Row(
        children: [
          if (scanning) const PulsingDot() else const SizedBox(width: 10),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              scanning ? '正在扫描附近设备…' : '扫描已停止 · 发现 $count 个',
              style: TextStyle(
                color: scanning ? AppTheme.accent : AppTheme.textDim,
                fontSize: 14,
              ),
            ),
          ),
          TextButton(
            onPressed: onToggle,
            child: Text(scanning ? '停止' : '扫描',
                style: const TextStyle(color: AppTheme.accent)),
          ),
        ],
      ),
    );
  }
}

class _DeviceCard extends StatelessWidget {
  final ScanResult result;
  final VoidCallback onTap;

  const _DeviceCard({required this.result, required this.onTap});

  /// 广播名形如 PhoneCtl-2026.10.21-ci7，把版本拆出来单独渲染更易读。
  (String, String) _splitName(String name) {
    final i = name.indexOf('-');
    if (i <= 0 || i == name.length - 1) return (name, '');
    return (name.substring(0, i), name.substring(i + 1));
  }

  @override
  Widget build(BuildContext context) {
    final rawName =
        result.advertisementData.advName.isNotEmpty
            ? result.advertisementData.advName
            : (result.device.platformName.isNotEmpty
                ? result.device.platformName
                : '未命名设备');
    final (title, version) = _splitName(rawName);
    final rssi = result.rssi;
    final (label, color) = rssi > -60
        ? ('强', AppTheme.accent)
        : rssi > -75
            ? ('中', AppTheme.warn)
            : ('弱', AppTheme.textDim);

    return Material(
      color: AppTheme.surface,
      borderRadius: BorderRadius.circular(14),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(14),
        child: Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: AppTheme.border),
          ),
          child: Row(
            children: [
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  color: AppTheme.surfaceHi,
                  borderRadius: BorderRadius.circular(11),
                ),
                child: const Icon(Icons.memory, color: AppTheme.accent, size: 22),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title,
                        style: const TextStyle(
                            color: AppTheme.text,
                            fontSize: 16,
                            fontWeight: FontWeight.w600)),
                    if (version.isNotEmpty) ...[
                      const SizedBox(height: 3),
                      Text(version,
                          style: AppTheme.mono
                              .copyWith(color: AppTheme.textDim, fontSize: 12)),
                    ],
                  ],
                ),
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text('$rssi dBm',
                      style: AppTheme.mono
                          .copyWith(color: color, fontSize: 12)),
                  const SizedBox(height: 3),
                  Text(label,
                      style: TextStyle(color: color, fontSize: 11)),
                ],
              ),
              const SizedBox(width: 6),
              const Icon(Icons.chevron_right, color: AppTheme.textDim, size: 20),
            ],
          ),
        ),
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  final bool scanning;

  const _EmptyState({required this.scanning});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(scanning ? Icons.search : Icons.bluetooth_searching,
                size: 56, color: AppTheme.textDim.withOpacity(0.5)),
            const SizedBox(height: 20),
            Text(
              scanning ? '正在寻找板子…' : '还没发现设备',
              style: const TextStyle(
                  color: AppTheme.text, fontSize: 17, fontWeight: FontWeight.w500),
            ),
            const SizedBox(height: 12),
            const Text(
              '确认板子已上电，广播名以 PhoneCtl- 开头。\n如果刚刷完固件，等它重启完成再扫。',
              textAlign: TextAlign.center,
              style: TextStyle(color: AppTheme.textDim, fontSize: 13, height: 1.6),
            ),
          ],
        ),
      ),
    );
  }
}
