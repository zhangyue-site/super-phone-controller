import 'dart:async';
import 'package:flutter/material.dart';
import 'app_release.dart';
import 'control_client.dart';
import 'device_screen.dart';
import 'target_session.dart';

class ProductAppearance extends InheritedWidget {
  const ProductAppearance(
      {super.key,
      required this.mode,
      required this.onChanged,
      required super.child});
  final ThemeMode mode;
  final ValueChanged<ThemeMode> onChanged;
  static ProductAppearance? of(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<ProductAppearance>();
  @override
  bool updateShouldNotify(ProductAppearance oldWidget) =>
      oldWidget.mode != mode;
}

class ProductSettingsScreen extends StatefulWidget {
  const ProductSettingsScreen({super.key, this.client, this.diagnostic});
  final ControlClient? client;
  final String? diagnostic;
  @override
  State<ProductSettingsScreen> createState() => _ProductSettingsScreenState();
}

class _ProductSettingsScreenState extends State<ProductSettingsScreen> {
  String? _upgradeNotice;
  Timer? _timer;
  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(seconds: 2), (_) {
      if (mounted && widget.client != null) setState(() {});
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _message(String title, String body) => showDialog<void>(
      context: context,
      builder: (c) => AlertDialog(
              title: Text(title),
              content: SingleChildScrollView(child: Text(body)),
              actions: [
                TextButton(
                    onPressed: () => Navigator.pop(c), child: const Text('关闭'))
              ]));
  Future<void> _maintenance() async {
    if (widget.client?.usesBoardLink == true || TargetSession.hasGateway) {
      await _message('先释放当前蓝牙连接', '请先停止手机操作，在被控状态页释放手机中转连接，再进入蓝牙维护。屏幕共享可继续保留。');
      return;
    }
    if (!mounted) return;
    await Navigator.of(context)
        .push(MaterialPageRoute<void>(builder: (_) => const DeviceScreen()));
  }

  Future<void> _wifi() async {
    final accepted = await showDialog<bool>(
        context: context,
        builder: (c) => AlertDialog(
                title: const Text('检查控制板更新'),
                content: const Text(
                    '控制板会先检查版本。有更新时会中断手机操作并升级；请先停止当前任务。重启后需重新连接并核对版本，收到请求回执不代表升级成功。'),
                actions: [
                  TextButton(
                      onPressed: () => Navigator.pop(c, false),
                      child: const Text('继续当前任务')),
                  FilledButton(
                      onPressed: () => Navigator.pop(c, true),
                      child: const Text('检查并请求升级'))
                ]));
    if (accepted != true || !mounted) return;
    widget.client!.requestWifiUpgrade();
    setState(() => _upgradeNotice = '已请求控制板检查更新；完成状态需重启后核验。');
  }

  @override
  Widget build(BuildContext context) {
    final appearance = ProductAppearance.of(context);
    return Scaffold(
        appBar: AppBar(title: const Text('设置与设备维护')),
        body: ListView(padding: const EdgeInsets.all(20), children: [
          Text('外观', style: Theme.of(context).textTheme.titleLarge),
          RadioGroup<ThemeMode>(
              groupValue: appearance?.mode ?? ThemeMode.system,
              onChanged: (value) {
                if (value != null) appearance?.onChanged(value);
              },
              child: Column(children: [
                for (final entry in [
                  (ThemeMode.system, '跟随系统'),
                  (ThemeMode.light, '浅色'),
                  (ThemeMode.dark, '深色')
                ])
                  RadioListTile<ThemeMode>(
                      value: entry.$1, title: Text(entry.$2)),
              ])),
          const Divider(),
          ListTile(
              leading: const Icon(Icons.settings_ethernet),
              title: const Text('联网方式'),
              subtitle: const Text('控制板直连 Wi-Fi / 手机蓝牙中转'),
              onTap: () => _message('联网方式',
                  '控制板直连请在板端网络页设置 Wi-Fi。手机中转在连接页建立，同一时间只能有一台中转手机。切换前先停止操作并释放原连接。未取得实际状态时，App不会把蓝牙连接当作云端在线。')),
          Text('升级与恢复', style: Theme.of(context).textTheme.titleLarge),
          ListTile(
              leading: const Icon(Icons.system_update_alt),
              title: const Text('App 版本与更新'),
              subtitle: const Text('保留原应用，从官方下载页获取同签名新版'),
              onTap: () => AppRelease.show(context)),
          ListTile(
              leading: const Icon(Icons.wifi),
              title: const Text('控制板 Wi-Fi 升级'),
              subtitle: Text(widget.client?.canWifiUpgrade == true
                  ? '先检查版本，再按控制板实际阶段更新'
                  : '当前连接尚不可从此手机发起，可在控制板上检查更新'),
              onTap: widget.client?.canWifiUpgrade == true
                  ? _wifi
                  : () => _message('控制板 Wi-Fi 升级',
                      '请在控制板的升级入口操作，或先建立此手机的蓝牙中转连接。网络连接成功不代表云端授权有效。')),
          if (widget.client?.canWifiUpgrade == true)
            Padding(
                padding: const EdgeInsets.all(12),
                child: Text(widget.client!.upgradeStatus)),
          if (_upgradeNotice != null && widget.client?.canWifiUpgrade != true)
            const Text('连接已中断，升级结果待核验。请重新连接并核对版本。'),
          if (_upgradeNotice != null)
            Padding(
                padding: const EdgeInsets.all(12),
                child: Text(_upgradeNotice!)),
          ListTile(
              leading: const Icon(Icons.bluetooth),
              title: const Text('蓝牙固件维护'),
              subtitle: const Text('无需 USB 或本机屏幕共享；保留官方固件下载与本地镜像恢复'),
              onTap: _maintenance),
          const Divider(),
          Text('控制板功能', style: Theme.of(context).textTheme.titleLarge),
          ListTile(
              leading: const Icon(Icons.volume_up_outlined),
              title: const Text('声音与试听'),
              subtitle: const Text('音量、静音和试听可在控制板上调节'),
              onTap: () =>
                  _message('声音与试听', '请在控制板的声音入口调节音量、静音或试听。App 远程声音控制尚未接通。')),
          ListTile(
              leading: const Icon(Icons.touch_app_outlined),
              title: const Text('语音、手动控制与额度'),
              subtitle: const Text('保留原控制板能力与专项技能概念'),
              onTap: () => _message('控制板上的功能',
                  '语音、方向与点击、返回与桌面、额度和网络方式仍在控制板上可用。未接通的 App 远程入口不会假装已执行。技能可保存，当前云端回放仍在联调。')),
          ListTile(
              leading: const Icon(Icons.info_outline),
              title: const Text('连接诊断与兼容说明'),
              subtitle: const Text('查看底层连接信息与输入兼容范围'),
              onTap: () => _message('连接诊断与兼容说明',
                  '${widget.diagnostic ?? widget.client?.connectionStatus ?? '当前没有设备诊断数据'}\n\n中文输入使用被控手机现有输入法、可见候选与控制板 USB 键盘。结果需按画面核验，不能保证所有输入法或键盘布局都一致。正常使用不要求开启开发者调试。')),
        ]));
  }
}
