import 'dart:convert';
import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'ble_ota_service.dart';
import 'control_client.dart';
import 'screen_share.dart';
import 'usb_launch.dart';

/// The target owns capture and the BLE relay, never command entry.
class UsbTargetScreen extends StatefulWidget {
  final UsbAttachment attachment;
  final BleOtaService? service;
  final VoidCallback? onLegacy;
  final bool Function() isCurrent;
  const UsbTargetScreen(
      {super.key,
      required this.attachment,
      required this.isCurrent,
      this.service,
      this.onLegacy});
  @override
  State<UsbTargetScreen> createState() => _UsbTargetScreenState();
}

class _UsbTargetScreenState extends State<UsbTargetScreen> {
  static final Set<String> _manuallyStopped = <String>{};
  Timer? _timer;
  ControlClient? _control;
  Future<void>? _startFuture;
  bool _busy = false, _active = false, _polling = false, _stopping = false;
  bool _pointerReady = false, _lost = false, _externalGateway = false;
  int _generation = 0;
  String _capture = '等待屏幕共享授权', _relay = '尚未连接';
  String? _error, _code;
  DateTime? _codeExpiry;
  DateTime? _captureRenewed;
  bool? _expectedWindowMode;
  bool _current(int generation) =>
      mounted && !_lost && widget.isCurrent() && generation == _generation;

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(seconds: 2), (_) => _poll());
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_manuallyStopped.contains(widget.attachment.serial)) _start();
    });
  }

  Future<void> _stopCapture() => ScreenShare.channel
      .invokeMethod<void>('stop', {'usbSession': widget.attachment.session});

  Future<void> _poll() async {
    if (_polling || _busy || _stopping || !mounted || _lost) return;
    _polling = true;
    final generation = _generation;
    try {
      if (!widget.isCurrent()) {
        _lost = true;
        _generation++;
        await _control?.shutdown();
        await _stopCapture();
        if (mounted) {
          setState(() {
            _active = false;
            _relay = 'USB 已断开，控制已停止';
          });
        }
        return;
      }
      final status = await ScreenShare.status();
      final active = await ScreenShare.isActive();
      if (!_current(generation)) return;
      if (!active && _active) {
        await _control?.shutdown();
        if (!_current(generation)) return;
      }
      if (active) await _usbWindow(generation);
      if (!_current(generation)) return;
      await _control?.refresh();
      if (_active &&
          active &&
          _captureRenewed != null &&
          DateTime.now().difference(_captureRenewed!).inSeconds >= 60) {
        await ScreenShare.renewUsb(widget.attachment);
        _captureRenewed = DateTime.now();
      }
      if (!_current(generation)) return;
      setState(() {
        _active = active;
        _capture = status.capture;
        _pointerReady = status.pointerReady;
        if (_control != null && !_control!.authorized) {
          _relay = '连接已结束，请重新连接；旧动作不会重发';
        }
        if (_codeExpiry != null && DateTime.now().isAfter(_codeExpiry!)) {
          _code = null;
        }
      });
    } catch (e) {
      if (_current(generation)) setState(() => _error = '状态检查失败：$e');
    } finally {
      _polling = false;
    }
  }

  Future<void> _usbWindow(int generation) async {
    Future<Map<String, dynamic>> request(Map<String, dynamic> body) async {
      final raw = await ScreenShare.channel.invokeMethod<String>('usbWindow', {
        'usbSession': widget.attachment.session,
        'body': jsonEncode(body),
      });
      if (!_current(generation)) throw StateError('USB窗口会话已改变');
      final value = jsonDecode(raw ?? '{}');
      if (value is! Map<String, dynamic>) {
        throw const FormatException('USB窗口响应无效');
      }
      return value;
    }

    final window = await request({'operation': 'poll'});
    if (window['state'] == 'idle') return;
    final nonce = window['nonce'],
        mode = window['mode'],
        revision = window['generation'],
        ttl = window['expiresInMs'];
    if (window['state'] != 'prepare' ||
        nonce is! String ||
        !RegExp(r'^[0-9a-f]{32}$').hasMatch(nonce) ||
        (mode != 'hid' && mode != 'normal') ||
        revision is! int ||
        ttl is! int ||
        ttl < 1 ||
        ttl > 5000) {
      throw const FormatException('USB切换窗口无效');
    }
    await UsbLaunch.channel.invokeMethod<void>('expectMode',
        {'session': widget.attachment.session, 'hid': mode == 'hid'});
    if (!_current(generation)) return;
    _expectedWindowMode = mode == 'hid';
    final ready = await request({
      'operation': 'ready',
      'nonce': nonce,
      'mode': mode,
      'generation': revision
    });
    if (ready['state'] != 'ready') throw StateError('USB切换窗口未确认');
  }

  Future<String> _usbIdentity() async {
    final info = await UsbLaunch.channel.invokeMapMethod<String, dynamic>(
        'info', {'session': widget.attachment.session});
    final device = info?['device'];
    if (info?['protocol'] != 1 ||
        info?['usbSerial'] != widget.attachment.serial ||
        device is! String ||
        !RegExp(r'^[A-Za-z0-9_-]{1,64}$').hasMatch(device)) {
      throw StateError('无法核验 USB 控制板身份');
    }
    return device;
  }

  Future<void> _connectBoard(String identity, int generation) async {
    final service = widget.service;
    if (service == null) {
      _relay = '等待控制板连接';
      return;
    }
    await _control?.shutdown();
    if (!_current(generation)) return;
    final devices = <String, BluetoothDevice>{};
    final bound = widget.attachment.remoteId;
    final sub = service.scanResults.listen((results) {
      for (final result in results) {
        final id = result.device.remoteId.str.toUpperCase();
        if (bound == null || id == bound) devices[id] = result.device;
      }
    });
    try {
      await service.startScan();
      final until = DateTime.now().add(const Duration(seconds: 10));
      while (_current(generation) && DateTime.now().isBefore(until)) {
        if (devices.isNotEmpty && bound != null) break;
        await Future<void>.delayed(const Duration(milliseconds: 250));
      }
    } finally {
      await service.stopScan();
      await sub.cancel();
    }
    if (!_current(generation)) return;
    if (devices.isEmpty) throw StateError('未找到对应控制板，请检查手机蓝牙与附近设备权限');
    for (final device in devices.values.take(8)) {
      try {
        await service.connect(device);
        if (!_current(generation)) {
          await service.disconnect();
          return;
        }
        final info = await service.readInfo();
        if (!_current(generation)) {
          await service.disconnect();
          return;
        }
        if (info == null || info.device != identity) {
          await service.disconnect();
          continue;
        }
        widget.attachment.validateBoard(device.remoteId.str, info.device);
        if (!service.supportsLocalControl) throw StateError('当前控制板固件不支持安全中继');
        final control = ControlClient();
        _control = control;
        control.onModeChange = (hid) async {
          if (!_current(generation) || !_active || _stopping) {
            throw StateError('共享或 USB 会话已失效');
          }
          if (_expectedWindowMode == hid) {
            _expectedWindowMode = null;
            return;
          }
          await UsbLaunch.channel.invokeMethod<void>(
              'expectMode', {'session': widget.attachment.session, 'hid': hid});
        };
        await control.authorize(service);
        if (!_current(generation)) {
          await control.shutdown();
          return;
        }
        await UsbLaunch.bind(
            widget.attachment, device.remoteId.str, info.device);
        _relay = '已连接，等待控制手机或龙虾的任务';
        return;
      } catch (_) {
        await _control?.shutdown();
        await service.disconnect();
        rethrow;
      }
    }
    throw StateError('蓝牙设备与 USB 控制板身份不一致，未建立控制连接');
  }

  Future<void> _start() {
    if (_startFuture != null) return _startFuture!;
    final future = _performStart();
    _startFuture = future;
    return future.whenComplete(() {
      _startFuture = null;
    });
  }

  Future<void> _performStart() async {
    if (_busy || _stopping || !widget.isCurrent()) return;
    _manuallyStopped.remove(widget.attachment.serial);
    final generation = ++_generation;
    setState(() {
      _busy = true;
      _error = null;
      _code = null;
      _relay = '正在核验控制板';
    });
    try {
      final identity = await _usbIdentity();
      if (!_current(generation)) return;
      if (!await ScreenShare.isActive()) {
        await ScreenShare.startUsb(widget.attachment,
            isCurrent: () => _current(generation));
      }
      final until = DateTime.now().add(const Duration(seconds: 5));
      while (_current(generation) &&
          !await ScreenShare.isActive() &&
          DateTime.now().isBefore(until)) {
        await Future<void>.delayed(const Duration(milliseconds: 100));
      }
      if (!_current(generation)) return;
      _active = await ScreenShare.isActive();
      _captureRenewed = DateTime.now();
      if (!_current(generation)) return;
      if (!_active) throw StateError('屏幕共享尚未启动，请重试');
      setState(() {
        _capture = '正在共享整个屏幕';
        _relay = '正在连接云端中继';
      });
      if (!_externalGateway) {
        await _connectBoard(identity, generation);
      } else {
        _relay = '本机蓝牙已释放；等待控制手机网关或板端 Wi-Fi';
      }
    } catch (e) {
      if (_current(generation)) setState(() => _error = '连接未完成：$e');
    } finally {
      if (mounted && generation == _generation) setState(() => _busy = false);
    }
  }

  Future<void> _pairingCode() async {
    if (_busy || _stopping || _control?.authorized != true) return;
    final generation = _generation;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final result = await _control!.pairingCode();
      final code = result['code'];
      if (code is! String ||
          !RegExp(r'^[A-Za-z0-9_-]{43}$').hasMatch(code) ||
          result['expiresIn'] != 120) {
        throw StateError('绑定码无效');
      }
      if (_current(generation)) {
        setState(() {
          _code = code;
          _codeExpiry = DateTime.now().add(const Duration(seconds: 120));
        });
      }
    } catch (e) {
      if (_current(generation)) setState(() => _error = '无法生成连接码：$e');
    } finally {
      if (mounted && generation == _generation) setState(() => _busy = false);
    }
  }

  Future<void> _stop() async {
    if (_stopping) return;
    _manuallyStopped.add(widget.attachment.serial);
    _generation++;
    setState(() {
      _stopping = true;
      _code = null;
      _error = null;
    });
    String? failure;
    try {
      await _stopCapture();
    } catch (e) {
      failure = '共享停止未确认：$e';
    }
    try {
      if (_control?.canReadStatus == true) await _control!.revokeControllers();
    } catch (e) {
      failure = '云端停止未确认：$e';
    } finally {
      await _control?.shutdown();
      await _startFuture;
      await widget.service?.disconnect();
      if (mounted) {
        setState(() {
          _active = false;
          _pointerReady = false;
          _busy = false;
          _stopping = false;
          _capture = '已停止共享';
          _relay = '控制连接已关闭';
          _error = failure;
        });
      }
    }
  }

  @override
  void dispose() {
    _generation++;
    _timer?.cancel();
    unawaited(_control?.shutdown() ?? Future<void>.value());
    unawaited(_stopCapture().catchError((_) {}));
    super.dispose();
  }

  Widget _row(IconData icon, String label, String value) =>
      ListTile(leading: Icon(icon), title: Text(label), subtitle: Text(value));

  @override
  Widget build(BuildContext context) {
    final connected = _control?.authorized == true;
    final ready =
        _active && (connected || _externalGateway) && widget.isCurrent();
    return Scaffold(
      appBar: AppBar(title: const Text('被控手机')),
      body: ListView(padding: const EdgeInsets.all(20), children: [
        Text(
            ready
                ? '已就绪'
                : _busy
                    ? '正在连接'
                    : '需要连接',
            style: Theme.of(context).textTheme.headlineMedium),
        const SizedBox(height: 8),
        const Text('接收控制手机或龙虾发起的任务，由控制板执行操作。'),
        const SizedBox(height: 20),
        Card(
            child: Column(children: [
          _row(
              Icons.usb,
              'USB 控制板',
              widget.isCurrent()
                  ? '已识别 · ${widget.attachment.serial}'
                  : '连接已改变'),
          _row(Icons.screen_share_outlined, '屏幕共享', _capture),
          _row(Icons.cloud_outlined, '云端中继', _relay),
          _row(Icons.touch_app_outlined, '执行许可',
              _pointerReady ? '已就绪' : '等待任务或板端许可'),
        ])),
        if (_error != null)
          Padding(
              padding: const EdgeInsets.symmetric(vertical: 12),
              child: Text(_error!,
                  style:
                      TextStyle(color: Theme.of(context).colorScheme.error))),
        const SizedBox(height: 16),
        if (!ready)
          FilledButton.icon(
              onPressed:
                  _busy || _stopping || !widget.isCurrent() ? null : _start,
              icon: const Icon(Icons.link),
              label: Text(_busy
                  ? '正在请求授权或连接…'
                  : _active
                      ? '重新连接云端中继'
                      : '开始屏幕共享并连接')),
        if (connected)
          OutlinedButton.icon(
              onPressed: _busy || _stopping ? null : _pairingCode,
              icon: const Icon(Icons.devices),
              label: const Text('连接控制手机')),
        if (!_externalGateway)
          OutlinedButton.icon(
              onPressed: _busy || _stopping
                  ? null
                  : () async {
                      setState(() => _busy = true);
                      try {
                        await _control?.shutdown();
                        await widget.service?.disconnect();
                        if (mounted) {
                          setState(() {
                            _externalGateway = true;
                            _control = null;
                            _code = null;
                            _relay = '本机蓝牙已释放，USB画面继续共享；请在控制手机接管网关或使用板端Wi-Fi';
                          });
                        }
                      } catch (e) {
                        if (mounted) setState(() => _error = '交接未完成：$e');
                      } finally {
                        if (mounted) setState(() => _busy = false);
                      }
                    },
              icon: const Icon(Icons.bluetooth_disabled),
              label: const Text('释放蓝牙网关，保留USB共享')),
        if (_code != null)
          Card(
              child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        const Text('在控制手机中粘贴连接码。两分钟内有效，仅可使用一次；请只交给自己的控制手机。'),
                        const SizedBox(height: 12),
                        SelectableText(_code!),
                        TextButton.icon(
                            onPressed: () async {
                              await Clipboard.setData(
                                  ClipboardData(text: _code!));
                            },
                            icon: const Icon(Icons.copy),
                            label: const Text('复制连接码')),
                      ]))),
        const SizedBox(height: 16),
        const Text('屏幕画面上传至云端用于理解任务和核验结果。停止后需重新连接和授权，未确认的旧动作不会重发。'),
      ]),
      bottomNavigationBar: SafeArea(
          child: Padding(
              padding: const EdgeInsets.all(16),
              child: OutlinedButton.icon(
                  onPressed: _stopping ? null : _stop,
                  icon: const Icon(Icons.stop_circle_outlined),
                  label: Text(_stopping ? '正在停止…' : '停止控制与共享')))),
    );
  }
}
