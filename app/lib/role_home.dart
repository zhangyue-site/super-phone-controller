import 'package:flutter/material.dart';
import 'product_settings.dart';
import 'product_widgets.dart';

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
      body: SafeArea(
        top: false,
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 840),
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    if (sharingActive) ...[
                      _RoleTile(
                        icon: Icons.screen_share_outlined,
                        title: '屏幕共享仍在继续',
                        description: '点此返回被控手机页面，可查看状态或停止共享',
                        onTap: onTarget,
                      ),
                      const SizedBox(height: 12),
                    ],
                    const ProductHeader(
                      icon: Icons.devices_other_outlined,
                      label: '双手机工作台',
                      title: '让两台手机连接起来',
                      description: '在两台手机上分别选角色：一台发任务，另一台接控制板并共享画面。',
                    ),
                    const ProductSectionTitle('选择这台手机的用途'),
                    LayoutBuilder(builder: (context, constraints) {
                      final tiles = [
                        _RoleTile(
                          icon: Icons.send_outlined,
                          title: '控制手机',
                          description: '发送任务、查看进度，无需共享本机屏幕',
                          onTap: onController,
                        ),
                        _RoleTile(
                          icon: Icons.phone_android,
                          title: '被控手机',
                          description: '连接控制板，并按系统提示共享屏幕',
                          onTap: onTarget,
                        ),
                      ];
                      final wide = constraints.maxWidth >=
                          600 * MediaQuery.textScalerOf(context).scale(16) / 16;
                      final width = wide
                          ? (constraints.maxWidth - 12) / 2
                          : constraints.maxWidth;
                      return Wrap(spacing: 12, runSpacing: 12, children: [
                        for (final tile in tiles)
                          SizedBox(width: width, child: tile),
                      ]);
                    }),
                    if (onMaintenance case final maintenance?) ...[
                      const ProductSectionTitle('设备维护'),
                      _RoleTile(
                        icon: Icons.system_update_outlined,
                        title: '蓝牙固件维护',
                        description: '先停止控制并释放原手机中转，再维护；无需 USB 或共享本机屏幕',
                        onTap: maintenance,
                      ),
                    ],
                  ]),
            ),
          ),
        ),
      ),
    );
  }
}

class _RoleTile extends StatelessWidget {
  const _RoleTile(
      {required this.icon,
      required this.title,
      required this.description,
      required this.onTap});

  final IconData icon;
  final String title, description;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Card(
        margin: EdgeInsets.zero,
        clipBehavior: Clip.antiAlias,
        child: ListTile(
          minTileHeight: 88,
          contentPadding:
              const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          leading: ProductIcon(icon),
          title: Text(title, style: Theme.of(context).textTheme.titleMedium),
          subtitle: Text(description),
          trailing: const Icon(Icons.chevron_right),
          onTap: onTap,
        ),
      );
}
