import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'controller_pair_screen.dart';
import 'device_screen.dart';
import 'role_home.dart';
import 'theme.dart';
import 'usb_launch.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const PcFlashApp());
}

class PcFlashApp extends StatefulWidget {
  const PcFlashApp({super.key});
  @override
  State<PcFlashApp> createState() => _PcFlashAppState();
}

class _PcFlashAppState extends State<PcFlashApp> {
  static const _appChannel = MethodChannel('pcflash/app');
  ThemeMode _themeMode = ThemeMode.system;
  int _appearanceRevision = 0;

  @override
  void initState() {
    super.initState();
    unawaited(_restoreAppearance());
  }

  Future<void> _restoreAppearance() async {
    final revision = _appearanceRevision;
    try {
      final saved = await _appChannel.invokeMethod<String>('appearance');
      if (!mounted || revision != _appearanceRevision) return;
      final mode = switch (saved) {
        'light' => ThemeMode.light,
        'dark' => ThemeMode.dark,
        _ => ThemeMode.system,
      };
      setState(() => _themeMode = mode);
    } catch (_) {/* Unavailable preferences keep the system default. */}
  }

  void _setAppearance(ThemeMode mode) {
    _appearanceRevision++;
    setState(() => _themeMode = mode);
    unawaited(_saveAppearance(mode));
  }

  Future<void> _saveAppearance(ThemeMode mode) async {
    try {
      await _appChannel
          .invokeMethod<void>('setAppearance', {'mode': mode.name});
    } catch (_) {/* The selected theme remains available for this session. */}
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: '手机控制助手',
        debugShowCheckedModeBanner: false,
        theme: AppTheme.light(),
        darkTheme: AppTheme.build(),
        themeMode: _themeMode,
        home:
            _RoleRouter(themeMode: _themeMode, onThemeChanged: _setAppearance),
      );
}

class _RoleRouter extends StatefulWidget {
  const _RoleRouter({required this.themeMode, required this.onThemeChanged});
  final ThemeMode themeMode;
  final ValueChanged<ThemeMode> onThemeChanged;
  @override
  State<_RoleRouter> createState() => _RoleRouterState();
}

class _RoleRouterState extends State<_RoleRouter> {
  bool _selected = false;
  @override
  void initState() {
    super.initState();
    _checkAttachedTarget();
  }

  Future<void> _checkAttachedTarget() async {
    try {
      final attachment = await UsbLaunch.snapshot();
      if (mounted && !_selected && attachment != null) _openTarget();
    } catch (_) {
      /* Role selection remains available when USB is unavailable. */
    }
  }

  Future<void> _open(Widget screen) async {
    if (_selected) return;
    _selected = true;
    await Navigator.of(context)
        .push(MaterialPageRoute<void>(builder: (_) => screen));
    if (mounted) _selected = false;
  }

  void _openTarget() => _open(const DeviceScreen(targetOnly: true));
  @override
  Widget build(BuildContext context) => RoleHome(
        themeMode: widget.themeMode,
        onThemeChanged: widget.onThemeChanged,
        onController: () => _open(const ControllerPairScreen()),
        onTarget: _openTarget,
        onMaintenance: () => _open(const DeviceScreen()),
      );
}
