import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'ble_ota_service.dart';
import 'control_client.dart';
import 'gateway_recovery.dart';
import 'screen_share.dart';
import 'screen_task_status.dart';
import 'target_progress_card.dart';
import 'product_widgets.dart';

/// iOS uses explicit BLE possession and system broadcast consent.
/// It never invents a USB CDC attachment or claims HID phone compatibility.
class IosTargetScreen extends StatefulWidget {
  const IosTargetScreen({super.key, this.service});
  final BleOtaService? service;
  @override
  State<IosTargetScreen> createState() => _IosTargetScreenState();
}

class _IosTargetScreenState extends State<IosTargetScreen> {
  late final BleOtaService _service = widget.service ?? BleOtaService();
  final _recovery = GatewayRecoveryGate();
  final _devices = <String, ScanResult>{};
  StreamSubscription<List<ScanResult>>? _scan;
  Timer? _timer;
  ControlClient? _client;
  BluetoothDevice? _board;
  bool _confirmed = false, _busy = false, _polling = false, _active = false;
  int _generation = 0;
  bool _disposing = false;
  bool get _alive => mounted && !_disposing;
  Future<void>? _stopping;
  String? _error, _code, _stopNote;
  DateTime? _renewed, _codeExpiry;
  ScreenTaskStatus _feedback = const ScreenTaskStatus(capture: '尚未共享');

  bool _current(int generation) => _alive && generation == _generation;
  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(seconds: 2), (_) => _poll());
  }

  Future<void> _search() async {
    if (_busy || _client != null) return;
    setState(() {
      _error = null;
      _devices.clear();
    });
    _scan ??= _service.scanResults.listen((values) {
      if (!_alive || _client != null) return;
      setState(() {
        for (final value in values) {
          _devices[value.device.remoteId.str] = value;
        }
      });
    });
    try {
      await _service.startScan();
    } catch (e) {
      if (_alive) setState(() => _error = '扫描失败：$e');
    }
  }

  Future<void> _connect(ScanResult result) async {
    if (_busy || !_confirmed || _client != null) return;
    final generation = ++_generation;
    setState(() {
      _busy = true;
      _error = null;
      _stopNote = null;
    });
    final client = ControlClient();
    _client = client;
    _board = result.device;
    try {
      await _service.stopScan();
      await _service.connect(result.device);
      if (!_current(generation)) return;
      if (!_service.supportsLocalControl) {
        throw StateError('请先升级控制板至支持签名手机中转的固件');
      }
      await client.authorize(_service);
      if (!_current(generation)) return;
      await ScreenShare.start(_service, isCurrent: () => _current(generation));
      if (!_current(generation)) return;
      if (!await ScreenShare.isActive()) throw StateError('系统尚未确认屏幕广播');
      await client.renewCapture();
      if (!_current(generation)) return;
      _renewed = DateTime.now();
      _recovery.reset();
      final pairing = await client.pairingCode();
      if (!_current(generation)) return;
      setState(() {
        _active = true;
        _code = pairing['code'] as String?;
        _codeExpiry = pairing['persistent'] == true
            ? null
            : DateTime.now().add(const Duration(seconds: 120));
      });
    } catch (e) {
      if (_current(generation)) {
        await _stop();
        if (_alive) setState(() => _error = '被控端连接未完成：$e');
      }
    } finally {
      if (_current(generation)) setState(() => _busy = false);
    }
  }

  Future<void> _newCode({bool rotate = false}) async {
    final client = _client;
    if (_busy || !_active || client == null) return;
    final generation = _generation;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final pairing = rotate
          ? await client.rotatePairingCode()
          : await client.pairingCode();
      if (_current(generation)) {
        setState(() {
          _code = pairing['code'] as String?;
          _codeExpiry = pairing['persistent'] == true
              ? null
              : DateTime.now().add(const Duration(seconds: 120));
          _error = null;
        });
      }
    } catch (e) {
      if (_current(generation)) setState(() => _error = '绑定码未更新：$e');
    } finally {
      if (_current(generation)) setState(() => _busy = false);
    }
  }

  Future<void> _manageBinding(bool rotate) async {
    final approved = await showDialog<bool>(
        context: context,
        builder: (c) => AlertDialog(
                title: Text(rotate ? '更换绑定码？' : '解除控制手机？'),
                content: Text(rotate
                    ? '旧绑定码失效，已连接的控制手机将解除。系统屏幕广播保持。'
                    : '解除已连接的控制手机，保留固定绑定码。系统屏幕广播保持。'),
                actions: [
                  TextButton(
                      onPressed: () => Navigator.pop(c, false),
                      child: const Text('取消')),
                  FilledButton(
                      onPressed: () => Navigator.pop(c, true),
                      child: const Text('确认'))
                ]));
    if (approved != true || !_alive) return;
    if (rotate) {
      await _newCode(rotate: true);
      return;
    }
    final client = _client;
    if (client == null || _busy) return;
    setState(() => _busy = true);
    try {
      await client.revokeControllers();
    } catch (e) {
      if (_alive) setState(() => _error = '解除控制手机未确认：$e');
    } finally {
      if (_alive) setState(() => _busy = false);
    }
  }

  Future<void> _poll() async {
    final client = _client;
    if (_polling || _busy || client == null || !_active) return;
    _polling = true;
    final generation = _generation;
    try {
      final status = await ScreenShare.status();
      final active = await ScreenShare.isActive();
      if (!_current(generation)) return;
      if (!active) {
        await _stop();
        if (_alive) setState(() => _error = '系统已结束屏幕共享，控制已停止');
        return;
      }
      if (client.canRecoverGateway && _board != null) {
        await _recovery.tick(
          eligible: () => _current(generation) && client.canRecoverGateway,
          guard: () async =>
              _current(generation) && await ScreenShare.isActive(),
          run: (check) => client.recoverGateway(
            check: check,
            reconnect: () async {
              await _service.disconnect();
              await check();
              try {
                await _service.connect(_board!);
              } catch (e) {
                throw BleReconnectFailure(e);
              }
              final info = await _service.readInfo();
              if (info?.device != client.deviceId) throw StateError('控制板身份已改变');
            },
          ),
        );
      }
      await client.refresh();
      if (!_current(generation)) return;
      if (client.authorized &&
          (_renewed == null ||
              DateTime.now().difference(_renewed!).inSeconds >= 60)) {
        await client.renewCapture();
        if (!_current(generation)) return;
        _renewed = DateTime.now();
      }
      if (!_current(generation)) return;
      setState(() {
        _feedback = status;
        if (_codeExpiry != null && !DateTime.now().isBefore(_codeExpiry!)) {
          _code = null;
        }
        _error = client.authorized ? null : client.connectionStatus;
      });
    } catch (e) {
      if (_current(generation)) setState(() => _error = '连接检查未完成：$e');
    } finally {
      _polling = false;
    }
  }

  Future<void> _stop() =>
      _stopping ??= _stopNow().whenComplete(() => _stopping = null);

  Future<void> _stopNow() async {
    ++_generation;
    final client = _client;
    _client = null;
    _board = null;
    _active = false;
    _code = null;
    _renewed = null;
    if (_alive) {
      setState(() {
        _busy = true;
        _stopNote = '本机停止请求已发出；云端停止与已发动作结果仍需确认。';
      });
    }
    try {
      await ScreenShare.stop();
    } catch (_) {
      _stopNote = '系统屏幕广播停止未确认，请检查 iOS 广播状态；已发动作结果未知。';
    }
    try {
      await client?.shutdown();
    } finally {
      await _recovery.cancel();
      await _service.disconnect();
      if (_alive) setState(() => _busy = false);
    }
  }

  @override
  void dispose() {
    _disposing = true;
    _generation++;
    _timer?.cancel();
    unawaited(_scan?.cancel());
    unawaited(_stop());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => PopScope(
        canPop: _client == null && !_busy,
        onPopInvokedWithResult: (didPop, _) async {
          if (didPop || !mounted) return;
          final stop = await showDialog<bool>(
              context: context,
              builder: (c) => AlertDialog(
                    title: const Text('结束本次被控连接？'),
                    content: const Text('将停止系统屏幕广播和控制板中转。未完成的动作不会重放。'),
                    actions: [
                      TextButton(
                          onPressed: () => Navigator.pop(c, false),
                          child: const Text('继续连接')),
                      FilledButton(
                          onPressed: () => Navigator.pop(c, true),
                          child: const Text('停止并返回')),
                    ],
                  ));
          if (stop == true) {
            await _stop();
            if (context.mounted) Navigator.pop(context);
          }
        },
        child: Scaffold(
          appBar: AppBar(title: const Text('被控 iPhone')),
          bottomNavigationBar: SafeArea(
              child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: OutlinedButton.icon(
                      onPressed: _stop,
                      icon: const Icon(Icons.stop_circle_outlined),
                      label: Text(_busy ? '正在处理…' : '停止共享与控制')))),
          body: ListView(padding: const EdgeInsets.all(24), children: [
            Text(_active ? '系统屏幕广播中' : '连接控制板并共享本机屏幕',
                style: Theme.of(context).textTheme.headlineSmall),
            const SizedBox(height: 12),
            const Text(
                '通过蓝牙核验控制板身份，由 iOS 系统确认屏幕广播。控制板仍需通过 USB 连接本机才能执行 HID；蓝牙连接不代表 USB 或实际点击已通过。'),
            TargetStatusOverview(
                board: _client?.authorized == true
                    ? '蓝牙身份已核验；USB 实际连接未自动核验'
                    : '等待蓝牙身份核验；USB 实际连接未自动核验',
                capture: _active ? _feedback.capture : '等待 iOS 系统广播授权',
                network: _client?.authorized == true
                    ? '手机中转授权已建立；云端新鲜度见下方'
                    : '服务连接待确认',
                permission: 'iOS 不提供 Android USB 会话核验；实际 HID 兼容性须实机检查'),
            TargetProgressCard(
                status: _feedback,
                connected: _client?.authorized == true && _active,
                now: DateTime.now()),
            const Card(
                child: ListTile(
                    leading: Icon(Icons.text_snippet_outlined),
                    title: Text('本地 OCR · iOS 暂无支持'),
                    subtitle:
                        Text('本版本未接入 iOS 本地文字与按钮识别，不将 Android 模型状态视为本机可用。'))),
            if (_stopNote != null) ProductError(_stopNote!),
            CheckboxListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('我已将所选控制板的 USB 连接到这台 iPhone'),
              value: _confirmed,
              onChanged: _client != null || _busy
                  ? null
                  : (v) => setState(() => _confirmed = v == true),
            ),
            if (_error != null)
              Semantics(
                  liveRegion: true,
                  child: Text(_error!,
                      style: TextStyle(
                          color: Theme.of(context).colorScheme.error))),
            if (_client == null) ...[
              FilledButton(
                  onPressed: _confirmed && !_busy ? _search : null,
                  child: const Text('扫描控制板')),
              for (final result in _devices.values)
                ListTile(
                    title: Text(result.advertisementData.advName.isEmpty
                        ? '控制板'
                        : result.advertisementData.advName),
                    subtitle: Text(result.device.remoteId.str),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: _busy ? null : () => _connect(result)),
            ],
            if (_busy)
              const Padding(
                  padding: EdgeInsets.symmetric(vertical: 16),
                  child: LinearProgressIndicator()),
            if (_active) ...[
              const SizedBox(height: 20),
              if (_code != null)
                TargetBindingCode(
                    code: _code!, persistent: _codeExpiry == null),
              TextButton(
                  onPressed: _busy ? null : () => _newCode(),
                  child: const Text('查看绑定码')),
              if (_code != null && _codeExpiry == null)
                ExpansionTile(title: const Text('管理绑定'), children: [
                  TextButton(
                      onPressed: _busy ? null : () => _manageBinding(true),
                      child: const Text('更换绑定码并解除控制手机')),
                  TextButton(
                      onPressed: _busy ? null : () => _manageBinding(false),
                      child: const Text('解除控制手机，保留绑定码')),
                ]),
            ],
            const Text('返回时会询问是否停止系统广播；恢复连接不会重放旧操作。'),
          ]),
        ),
      );
}
