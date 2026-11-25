import 'app_maintenance_widgets.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'product_settings.dart';
import 'dart:async';
import 'dart:convert';
import 'screen_share.dart';
import 'target_session.dart';
import 'overlay_status.dart';
import 'human_pill_state.dart';
import 'task_history.dart';

class WirelessDebugCard extends StatefulWidget {
  const WirelessDebugCard({super.key});
  @override
  State<WirelessDebugCard> createState() => _WirelessDebugCardState();
}

class _WirelessDebugCardState extends State<WirelessDebugCard>
    with WidgetsBindingObserver {
  static const _channel = MethodChannel('pcflash/app');
  String _summary = '请在系统设置中确认';
  int _request = 0;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _refresh();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) _refresh();
  }

  Future<void> _refresh() async {
    final request = ++_request;
    var summary = '请在系统设置中确认';
    try {
      final status = await _channel
          .invokeMapMethod<String, Object?>('wirelessDebugStatus');
      final port = status?['port'];
      if (port is int && port >= 1 && port <= 65535) {
        summary = '系统报告的无线调试连接端口：$port';
      } else if (status?['enabled'] == true) {
        summary = '系统已开启，连接端口请在系统页查看';
      } else if (status?['enabled'] == false) {
        summary = '无线调试已关闭';
      }
    } on PlatformException {
      // Some systems withhold both signals.
    } on MissingPluginException {
      // This method is Android-only.
    }
    if (mounted && request == _request) setState(() => _summary = summary);
  }

  Future<void> _openSettings() async {
    try {
      await _channel.invokeMethod<void>('openDeveloperSettings');
    } on PlatformException catch (error) {
      if (!mounted) return;
      final message = error.code == 'sharing_active'
          ? '请先结束屏幕共享，再打开开发者选项'
          : '请从手机系统设置打开开发者选项';
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(message)));
    } on MissingPluginException {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('请从手机系统设置打开开发者选项')),
      );
    }
  }

  @override
  Widget build(BuildContext context) => Card(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('网络调试通道', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              Text(_summary),
              const SizedBox(height: 8),
              const Text('如需使用无线调试，请在系统设置中启用，并与自己的电脑配对。'),
              const SizedBox(height: 12),
              OutlinedButton(
                  onPressed: _openSettings, child: const Text('打开开发者选项')),
            ],
          ),
        ),
      );
}

/// Entry point for role selection; lifecycle and routing remain owned by caller.
class RoleHome extends StatelessWidget {
  const RoleHome(
      {super.key,
      required this.onController,
      required this.onTarget,
      this.themeMode = ThemeMode.system,
      this.onThemeChanged,
      this.onMaintenance,
      this.sharingActive = false});
  final VoidCallback onController;
  final VoidCallback onTarget;
  final VoidCallback? onMaintenance;
  final bool sharingActive;
  final ThemeMode themeMode;
  final ValueChanged<ThemeMode>? onThemeChanged;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('手机控制助手'), actions: [
        IconButton(
            tooltip: '设置',
            icon: const Icon(Icons.settings_outlined),
            onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(
                builder: (_) => const ProductSettingsScreen()))),
        if (onThemeChanged != null)
          PopupMenuButton<ThemeMode>(
              tooltip: '显示主题',
              initialValue: themeMode,
              onSelected: onThemeChanged,
              itemBuilder: (_) => const [
                    PopupMenuItem(value: ThemeMode.system, child: Text('跟随系统')),
                    PopupMenuItem(value: ThemeMode.light, child: Text('浅色')),
                    PopupMenuItem(value: ThemeMode.dark, child: Text('深色')),
                  ],
              icon: const Icon(Icons.brightness_6_outlined)),
      ]),
      body: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            const StatusCard(),
            const SizedBox(height: 6),
            const Text('控制手机发任务，被控手机出画面；每次执行前都会核对你确认过的许可。',
                style: TextStyle(fontSize: 12)),
            const SizedBox(height: 20),
            Text('选择这台手机的用途', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 12),
            if (sharingActive)
              Card(
                  child: ListTile(
                      leading: const Icon(Icons.screen_share_outlined),
                      title: const Text('屏幕共享仍在继续'),
                      subtitle: const Text('进入设置或查看任务不会停止共享'),
                      trailing: const Icon(Icons.chevron_right),
                      onTap: onTarget)),
            Card(
                child: ListTile(
                    contentPadding: const EdgeInsets.all(20),
                    leading: Icon(Icons.send_outlined, color: colors.primary),
                    title: const Text('控制手机'),
                    subtitle: const Text('发送任务、查看进度，无需共享本机屏幕'),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: onController)),
            const SizedBox(height: 12),
            Card(
                child: ListTile(
                    contentPadding: const EdgeInsets.all(20),
                    leading: Icon(Icons.phone_android, color: colors.primary),
                    title: const Text('被控手机'),
                    subtitle: const Text('连接控制板，并按系统提示共享屏幕'),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: onTarget)),
            const SizedBox(height: 12),
            Card(
                child: ListTile(
                    contentPadding: const EdgeInsets.all(20),
                    leading:
                        Icon(Icons.receipt_long, color: colors.primary),
                    title: const Text('任务记录'),
                    subtitle: const Text('最近任务的执行结果与回执'),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => Navigator.of(context).push(
                        MaterialPageRoute<void>(
                            builder: (_) => const TaskHistoryPage())))),
            const SizedBox(height: 12),
            Card(
                child: Theme(
                    data: Theme.of(context)
                        .copyWith(dividerColor: Colors.transparent),
                    child: ExpansionTile(
                        leading: Icon(Icons.tune, color: colors.primary),
                        title: const Text('高级工具'),
                        subtitle: const Text('固件维护 · 网络调试 · 诊断'),
                        childrenPadding:
                            const EdgeInsets.fromLTRB(16, 4, 16, 16),
                        children: [
              if (onMaintenance != null)
                ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: const Icon(Icons.system_update_outlined),
                    title: const Text('蓝牙固件维护'),
                    subtitle: const Text('控制板固件升级与回滚'),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: onMaintenance),
              if (Theme.of(context).platform == TargetPlatform.android) ...[
                const WirelessDebugCard(),
                const MaintenanceTile(),
              ],
            ]))),
          ])),
    );
  }
}

/// 首页状态仪表卡：四路信号灯 + 当前任务（HCI：状态可见 / 就近反馈）
class StatusCard extends StatefulWidget {
  const StatusCard({super.key});
  @override
  State<StatusCard> createState() => _StatusCardState();
}

class _StatusCardState extends State<StatusCard> {
  static const _channel = MethodChannel('pcflash/pill');
  Timer? _t;
  String _battery = '…';
  (String, Color) _share = ('共享检查中', Colors.orange);
  (String, Color) _hid = ('HID 未知', Colors.grey);
  String _task = '';

  @override
  void initState() {
    super.initState();
    _refresh();
    _t = Timer.periodic(const Duration(seconds: 5), (_) => _refresh());
  }

  @override
  void dispose() {
    _t?.cancel();
    super.dispose();
  }

  Future<void> _refresh() async {
    String battery = '电量?';
    var share = ('共享检查中', Colors.orange);
    var hid = ('HID 离线', Colors.orange);
    String task = '';
    try {
      final v = await _channel.invokeMethod<int>('battery');
      battery = (v is int && v >= 0 && v <= 100) ? '电量$v%' : '电量?';
    } catch (_) {}
    try {
      final raw = await ScreenShare.channel.invokeMethod<String>('status');
      final m = raw == null ? null : jsonDecode(raw);
      if (m is Map && m['active'] == true) {
        share = ('共享中', Colors.green);
      } else if (m is Map) {
        share = ('未共享', Colors.grey);
      }
    } catch (_) {}
    try {
      final client = TargetSession.retainedClient;
      final (_, text) = gatewayIndicator(
          hasClient: client != null,
          sessionReady: client?.authorized == true);
      hid = (
        text,
        client == null
            ? Colors.grey
            : (client.authorized == true ? Colors.green : Colors.orange)
      );
    } catch (_) {}
    try {
      task = HumanPillState.taskText;
    } catch (_) {}
    if (!mounted) return;
    setState(() {
      _battery = battery;
      _share = share;
      _hid = hid;
      _task = task;
    });
  }

  Widget _chip(Widget dot, String label) => Row(mainAxisSize: MainAxisSize.min, children: [
        dot,
        const SizedBox(width: 4),
        Text(label, style: const TextStyle(fontSize: 12)),
      ]);

  @override
  Widget build(BuildContext context) {
    Widget dot(Color c) => Container(
        width: 8,
        height: 8,
        decoration: BoxDecoration(color: c, shape: BoxShape.circle));
    return Card(
        child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Wrap(
                      spacing: 14,
                      runSpacing: 6,
                      children: [
                        _chip(dot(Colors.blue), _battery),
                        _chip(dot(_share.$2), _share.$1),
                        _chip(dot(_hid.$2), _hid.$1),
                      ]),
                  if (_task.isNotEmpty) ...[
                    const SizedBox(height: 8),
                    Text('当前任务：$_task',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                            fontSize: 13,
                            color: Theme.of(context).colorScheme.primary)),
                  ],
                ])));
  }
}
