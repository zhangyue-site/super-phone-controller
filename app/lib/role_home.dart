import 'package:flutter/material.dart';
import 'product_settings.dart';

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
            Text('选择这台手机的用途',
                style: Theme.of(context).textTheme.headlineMedium),
            const SizedBox(height: 12),
            const Text('控制手机发送任务，被控手机提供画面，控制板负责操作。连接建立后，每次执行仍会检查画面与许可。'),
            const SizedBox(height: 24),
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
          ])),
    );
  }
}
