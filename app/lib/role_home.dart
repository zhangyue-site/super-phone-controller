import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'product_settings.dart';

/// vc93: shows wireless-debugging / ADB status and the pairing code captured by the
/// accessibility auto-guide. Polls `adbGuideStatus` so it self-heals on every visit.
class AdbGuideCard extends StatefulWidget {
  const AdbGuideCard({super.key});
  @override
  State<AdbGuideCard> createState() => _AdbGuideCardState();
}

class _AdbGuideCardState extends State<AdbGuideCard> {
  static const _ch = MethodChannel('pcflash/app');
  Map<String, dynamic> _status = const {};
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    try {
      final r = await _ch.invokeMethod<dynamic>('adbGuideStatus');
      if (r is Map && mounted) {
        setState(() => _status = r.map((k, v) => MapEntry(k.toString(), v)));
      }
    } catch (_) {}
  }

  Future<void> _arm() async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      await _ch.invokeMethod<dynamic>('adbGuideArm');
      // The guide runs in the Settings UI; poll until it reports a result.
      for (var i = 0; i < 30; i++) {
        await Future.delayed(const Duration(seconds: 2));
        await _refresh();
        final code = _status['pairCode']?.toString() ?? '';
        final err = _status['err']?.toString() ?? '';
        if (code.isNotEmpty || (err.isNotEmpty && err != '')) break;
        if (!mounted) return;
      }
    } catch (_) {}
    if (mounted) setState(() => _busy = false);
    _refresh();
  }

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final port = _status['debugPort']?.toString() ?? '';
    final code = _status['pairCode']?.toString() ?? '';
    final pairPort = _status['pairPort']?.toString() ?? '';
    final err = _status['err']?.toString() ?? '';
    final wired = port.isNotEmpty;
    return Card(
        child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(children: [
                    Icon(wired ? Icons.usb_outlined : Icons.usb_off_outlined,
                        color: wired ? colors.primary : colors.error),
                    const SizedBox(width: 12),
                    Expanded(
                        child: Text('网络调试通道',
                            style: Theme.of(context).textTheme.titleMedium)),
                  ]),
                  const SizedBox(height: 8),
                  Text(wired ? '无线调试已开启，端口 $port' : '无线调试未开启',
                      style: TextStyle(
                          color: wired ? colors.primary : colors.error)),
                  if (code.isNotEmpty) ...[
                    const SizedBox(height: 8),
                    Text('配对码：$code'),
                    Text('配对地址：$pairPort'),
                    const SizedBox(height: 4),
                    Row(children: [
                      OutlinedButton(
                          onPressed: () async {
                            await Clipboard.setData(ClipboardData(
                                text: 'adb pair $pairPort $code'));
                            if (context.mounted) {
                              ScaffoldMessenger.of(context).showSnackBar(
                                  const SnackBar(content: Text('已复制配对命令')));
                            }
                          },
                          child: const Text('复制配对命令')),
                    ]),
                  ],
                  if (!wired && code.isEmpty) ...[
                    const SizedBox(height: 12),
                    Row(children: [
                      FilledButton(
                          onPressed: _busy ? null : _arm,
                          child: Text(_busy ? '引导中…（请看手机设置页）'
                              : '一键开启无线调试')),
                    ]),
                    if (err.isNotEmpty && err != 'timeout')
                      Text('引导信息：$err',
                          style: TextStyle(color: colors.error, fontSize: 12)),
                  ],
                ])));
  }
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
            const SizedBox(height: 12),
            const AdbGuideCard(),
          ])),
    );
  }
}
