import 'dart:io';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';

import 'ble_ota_service.dart';
import 'push_screen.dart';
import 'theme.dart';
import 'widgets.dart';

/// 屏幕 2：选固件。
///
/// 核心考量：BLE 传 1.3MB 要一两分钟，推错板子/推错文件的代价很大。
/// 所以在"开始推送"之前，把版本、大小、sha256 和板子当前版本摆在一起对比。
class FirmwareScreen extends StatefulWidget {
  final BleOtaService service;
  final BluetoothDevice device;

  const FirmwareScreen({
    super.key,
    required this.service,
    required this.device,
  });

  @override
  State<FirmwareScreen> createState() => _FirmwareScreenState();
}

class _FirmwareScreenState extends State<FirmwareScreen> {
  static const otaBase = 'https://controller.example.invalid/phone-controller';

  FirmwareInfo? _info;
  Uint8List? _bytes;
  int _chunkSize = 20;
  bool _busy = false;
  String? _error;
  String _deviceVersion = '';

  @override
  void initState() {
    super.initState();
    _deviceVersion = _parseVersion(widget.device.platformName);
    _prepare();
  }

  String _parseVersion(String name) {
    final i = name.indexOf('-');
    return i > 0 ? name.substring(i + 1) : '';
  }

  Future<void> _prepare() async {
    setState(() => _busy = true);
    try {
      final chunk = await widget.service.connect(widget.device);
      if (!mounted) return;
      setState(() {
        _chunkSize = chunk;
        _busy = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _error = '连接失败：$e';
      });
    }
  }

  Future<void> _pickLocal() async {
    final res = await FilePicker.pickFiles(
      type: FileType.any,
      withData: true,
    );
    final f = res?.files.single;
    if (f == null || f.bytes == null) return;
    await _loadBytes(f.bytes!, f.name);
  }

  Future<void> _fetchFromServer() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      // 服务器需要设备 token；客户端只做公开预览不可行，这里提示用户。
      // 实际部署时把 token 内嵌或让用户在设置里填。
      final res = await http
          .get(Uri.parse('$otaBase/firmware/image'))
          .timeout(const Duration(seconds: 30));
      if (res.statusCode != 200) {
        throw Exception('服务器返回 ${res.statusCode}（需要设备 token）');
      }
      await _loadBytes(res.bodyBytes, 'app.bin');
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _error = '从服务器获取失败：$e\n可以改用本地文件。';
      });
    }
  }

  Future<void> _loadBytes(Uint8List bytes, String name) async {
    if (!mounted) return;
    if (bytes.length < 4096) {
      setState(() {
        _busy = false;
        _error = '这个文件太小，不像是固件（< 4KB）';
      });
      return;
    }
    if (bytes.length > BleOtaService.maxImageSize) {
      setState(() {
        _busy = false;
        _error = '文件 ${(bytes.length / 1048576).toStringAsFixed(2)} MB '
            '超过 OTA 槽位上限 3.25 MB';
      });
      return;
    }

    // ESP32 app 镜像头：byte0 = 0xE9
    if (bytes[0] != 0xE9) {
      setState(() {
        _busy = false;
        _error = '文件头不是 ESP32 镜像（应为 0xE9），确认选的是 app.bin';
      });
      return;
    }

    final digest = sha256.convert(bytes).toString();
    // 版本号在 esp_app_desc_t 里，偏移 48 起 32 字节（与 124 的发布脚本一致）
    String version = '';
    if (bytes.length > 80) {
      final raw = bytes.sublist(48, 80);
      final end = raw.indexOf(0);
      version = String.fromCharCodes(raw.sublist(0, end < 0 ? 32 : end));
      // 只保留可打印字符，避免脏数据上屏
      version = version.replaceAll(RegExp(r'[^\x20-\x7E]'), '').trim();
    }

    final dir = await getTemporaryDirectory();
    final f = File('${dir.path}/$name');
    await f.writeAsBytes(bytes);

    setState(() {
      _bytes = bytes;
      _info = FirmwareInfo(
        name: name,
        size: bytes.length,
        sha256: digest,
        version: version.isEmpty ? '未知' : version,
      );
      _busy = false;
      _error = null;
    });
  }

  void _start() {
    if (_bytes == null || _info == null) return;
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => PushScreen(
        service: widget.service,
        device: widget.device,
        bytes: _bytes!,
        info: _info!,
        chunkSize: _chunkSize,
      ),
    ));
  }

  bool get _sameVersion =>
      _info != null && _deviceVersion.isNotEmpty && _info!.version == _deviceVersion;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('选择固件'),
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(22),
          child: Padding(
            padding: const EdgeInsets.only(left: 16, bottom: 10),
            child: Align(
              alignment: Alignment.centerLeft,
              child: Text(
                _deviceVersion.isEmpty
                    ? widget.device.remoteId.str
                    : '目标设备 · 当前 $_deviceVersion',
                style: AppTheme.mono
                    .copyWith(color: AppTheme.textDim, fontSize: 12),
              ),
            ),
          ),
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (_error != null) ...[
            InfoBanner(icon: Icons.error_outline, color: AppTheme.danger, text: _error!),
            const SizedBox(height: 16),
          ],
          _SourceCard(
            icon: Icons.cloud_download_outlined,
            title: '从服务器获取最新',
            subtitle: 'controller.example.invalid',
            primary: true,
            onTap: _busy ? null : _fetchFromServer,
          ),
          const SizedBox(height: 10),
          _SourceCard(
            icon: Icons.folder_open_outlined,
            title: '选择本地固件文件',
            subtitle: '从下载目录里挑 app.bin',
            onTap: _busy ? null : _pickLocal,
          ),
          if (_busy) ...[
            const SizedBox(height: 20),
            const Center(
              child: SizedBox(
                width: 22,
                height: 22,
                child: CircularProgressIndicator(strokeWidth: 2.4),
              ),
            ),
          ],
          if (_info != null) ...[
            const SizedBox(height: 26),
            const Text('已选固件',
                style: TextStyle(
                    color: AppTheme.textDim,
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    letterSpacing: 0.6)),
            const SizedBox(height: 10),
            _FirmwareDetail(info: _info!),
            if (_sameVersion) ...[
              const SizedBox(height: 12),
              InfoBanner(
                icon: Icons.warning_amber_rounded,
                text: '版本和板子当前版本相同（${_info!.version}），'
                    '通常不需要推送。如果是要回刷同一版本，可以继续。',
              ),
            ],
          ],
        ],
      ),
      bottomNavigationBar: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
          child: FilledButton(
            onPressed: (_info != null && !_busy && _error == null) ? _start : null,
            child: Text(_info == null ? '先选择一个固件' : '开始推送'),
          ),
        ),
      ),
    );
  }
}

class _SourceCard extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback? onTap;
  final bool primary;

  const _SourceCard({
    required this.icon,
    required this.title,
    required this.subtitle,
    this.onTap,
    this.primary = false,
  });

  @override
  Widget build(BuildContext context) {
    final accent = primary ? AppTheme.accent : AppTheme.text;
    return Material(
      color: primary ? AppTheme.accent.withOpacity(0.07) : AppTheme.surface,
      borderRadius: BorderRadius.circular(14),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(14),
        child: Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(14),
            border: Border.all(
                color: primary ? AppTheme.accent.withOpacity(0.45) : AppTheme.border),
          ),
          child: Row(
            children: [
              Icon(icon, color: accent, size: 22),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title,
                        style: TextStyle(
                            color: accent,
                            fontSize: 15,
                            fontWeight: FontWeight.w600)),
                    const SizedBox(height: 3),
                    Text(subtitle,
                        style: const TextStyle(
                            color: AppTheme.textDim, fontSize: 12)),
                  ],
                ),
              ),
              if (onTap != null)
                const Icon(Icons.chevron_right, color: AppTheme.textDim, size: 20),
            ],
          ),
        ),
      ),
    );
  }
}

class _FirmwareDetail extends StatelessWidget {
  final FirmwareInfo info;

  const _FirmwareDetail({required this.info});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppTheme.border),
      ),
      child: Column(
        children: [
          _row('文件', info.name, mono: false),
          const SizedBox(height: 12),
          _row('版本', info.version, mono: true),
          const SizedBox(height: 12),
          _row('大小', info.sizeText, mono: true),
          const SizedBox(height: 12),
          _row('sha256', '${info.sha256.substring(0, 16)}…', mono: true),
        ],
      ),
    );
  }

  Widget _row(String k, String v, {required bool mono}) {
    return Row(
      children: [
        SizedBox(
          width: 62,
          child: Text(k,
              style: const TextStyle(color: AppTheme.textDim, fontSize: 13)),
        ),
        Expanded(
          child: Text(
            v,
            style: (mono ? AppTheme.mono : const TextStyle())
                .copyWith(color: AppTheme.text, fontSize: 13),
            overflow: TextOverflow.ellipsis,
          ),
        ),
      ],
    );
  }
}
