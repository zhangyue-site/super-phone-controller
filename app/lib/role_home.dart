import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'product_settings.dart';

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
            Text('让两台手机连接起来',
                style: Theme.of(context).textTheme.headlineMedium),
            const SizedBox(height: 12),
            const Text('控制手机发送任务，被控手机提供画面，控制板负责操作。连接建立后，每次执行仍会检查画面与许可。'),
            const SizedBox(height: 24),
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
            if (onMaintenance != null) ...[
              const SizedBox(height: 12),
              Card(
                  child: ListTile(
                contentPadding: const EdgeInsets.all(20),
                leading:
                    Icon(Icons.system_update_outlined, color: colors.primary),
                title: const Text('蓝牙固件维护'),
                subtitle: const Text('先停止控制并释放原手机中转，再维护；无需 USB 或共享本机屏幕'),
                trailing: const Icon(Icons.chevron_right),
                onTap: onMaintenance,
              )),
            ],
            if (Theme.of(context).platform == TargetPlatform.android) ...[
              const SizedBox(height: 12),
              const WirelessDebugCard(),
            ],
          ])),
    );
  }
}
