import 'target_check_errors.dart';
import 'diagnostics.dart';
import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'ble_ota_service.dart';
import 'control_client.dart';
import 'screen_share.dart';
import 'usb_launch.dart';
import 'target_session.dart';
import 'product_widgets.dart';
import 'product_settings.dart';
import 'screen_task_status.dart';

/// The target owns capture and the BLE relay, never command entry.
class UsbTargetScreen extends StatefulWidget {
  final UsbAttachment attachment;
  final BleOtaService? service;
  final VoidCallback? onLegacy;
  final bool Function() isCurrent;
  final DateTime Function()? captureClock;
  final Future<void> Function(UsbAttachment)? renewCapture;
  const UsbTargetScreen(
      {super.key,
      required this.attachment,
      required this.isCurrent,
      this.service,
      this.onLegacy,
      this.captureClock,
      this.renewCapture});
  @override
  State<UsbTargetScreen> createState() => _UsbTargetScreenState();
}

class _UsbTargetScreenState extends State<UsbTargetScreen> {
  static final Set<String> _manuallyStopped = <String>{};
  static final Set<String> _autoAttemptedSessions = <String>{};
  Timer? _timer;
  ControlClient? _control;
  Future<void>? _startFuture;
  bool _busy = false, _active = false, _polling = false, _stopping = false;
  bool _pointerReady = false, _lost = false, _externalGateway = false;
  int _generation = 0;
  String _capture = '等待屏幕共享授权', _relay = '尚未连接';
  String? _error, _code;
  final _checkErrors = TargetCheckErrors();
  ScreenTaskStatus _feedback = const ScreenTaskStatus(capture: '状态待更新');
  DateTime? _codeExpiry;
  DateTime get _captureNow => widget.captureClock?.call() ?? DateTime.now();
  bool _current(int generation) =>
      mounted && !_lost && widget.isCurrent() && generation == _generation;

  @override
  void initState() {
    super.initState();
    TargetSession.addView(this);
    _timer = Timer.periodic(const Duration(seconds: 2), (_) => _poll());
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_manuallyStopped.contains(widget.attachment.serial)) {
        final first = _autoAttemptedSessions.add(widget.attachment.session);
        _start(allowConsent: first);
      }
    });
  }

  Future<void> _stopCapture() => ScreenShare.channel
      .invokeMethod<void>('stop', {'usbSession': widget.attachment.session});

  Future<void> _poll() async {
    if (_polling || _busy || _stopping || !mounted || _lost) return;
    _polling = true;
    final generation = _generation;
    var phase = TargetCheckPhase.status;
    try {
      if (!widget.isCurrent()) {
        SafeDiagnostics.record('target_release',
            phase: 'shutdown', reason: 'usb_unavailable');
        _lost = true;
        _generation++;
        _checkErrors.reset(_generation);
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
      setState(() => _checkErrors.succeed(TargetCheckPhase.status, generation));
      if (!active && _active) {
        SafeDiagnostics.record('target_release',
            phase: 'shutdown', reason: 'capture_inactive');
        await _control?.shutdown();
        if (!_current(generation)) return;
      }
      // Capture credentials recover independently of gateway/window errors.
      if (active) {
        try {
          await TargetSession.maintainCapture(widget.attachment,
              clock: widget.captureClock, renew: widget.renewCapture);
          if (_current(generation)) {
            setState(() =>
                _checkErrors.succeed(TargetCheckPhase.capture, generation));
          }
        } catch (e) {
          if (_current(generation)) {
            setState(() =>
                _checkErrors.fail(TargetCheckPhase.capture, e, generation));
          }
        }
      }
      if (!_current(generation)) return;
      try {
        if (active) {
          await _usbWindow(generation);
          if (_current(generation)) {
            setState(() =>
                _checkErrors.succeed(TargetCheckPhase.window, generation));
          }
        }
      } catch (e) {
        if (_current(generation)) {
          setState(
              () => _checkErrors.fail(TargetCheckPhase.window, e, generation));
        }
      }
      if (!_current(generation)) return;
      try {
        final control = _control;
        if (control?.authorized == true) {
          await control!.refresh();
          if (_current(generation) && control.authorized) {
            setState(
                () => _checkErrors.succeed(TargetCheckPhase.renew, generation));
          }
        }
      } catch (e) {
        if (_current(generation)) {
          setState(
              () => _checkErrors.fail(TargetCheckPhase.renew, e, generation));
        }
      }
      if (!_current(generation)) return;
      phase = TargetCheckPhase.recovery;
      final recovered =
          active && await TargetSession.maintainGateway(widget.attachment);
      if (!_current(generation)) return;
      setState(() {
        _active = active;
        _capture = status.capture;
        _feedback = status;
        _pointerReady = recovered ? false : status.pointerReady;
        if (recovered) {
          _checkErrors.succeed(TargetCheckPhase.recovery, generation);
          _checkErrors.succeed(TargetCheckPhase.renew, generation);
          _relay = '手机中转已恢复；旧任务已停止，请重新确认新任务';
        }
        if (_control != null && !_control!.authorized) {
          _relay = _control!.canRecoverGateway ||
                  _control!.gatewayRecoveryNeedsPairing
              ? TargetSession.recoveryStatus
              : '连接已结束，请重新连接；旧动作不会重发';
        }
        if (_codeExpiry != null && DateTime.now().isAfter(_codeExpiry!)) {
          _code = null;
        }
      });
    } catch (e) {
      if (_current(generation)) {
        setState(() => _checkErrors.fail(phase, e, generation));
      }
    } finally {
      _polling = false;
    }
  }

  Future<void> _usbWindow(int generation) =>
      TargetSession.window(widget.attachment);

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
    final retained = TargetSession.clientFor(widget.attachment);
    if (retained?.authorized == true) {
      TargetSession.resumeRecovery(retained!);
      _control = retained;
      _relay = '手机中转连接已保留';
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
        control.onModeChange = TargetSession.modeCallback(widget.attachment);
        await control.authorize(service);
        if (!_current(generation)) {
          await control.shutdown();
          return;
        }
        await UsbLaunch.bind(
            widget.attachment, device.remoteId.str, info.device);
        if (!_current(generation)) {
          await control.shutdown();
          await service.disconnect();
          return;
        }
        TargetSession.retain(widget.attachment, control, service);
        _relay = '手机中转已连接，执行前会检查画面与许可';
        return;
      } catch (_) {
        await _control?.shutdown();
        await service.disconnect();
        rethrow;
      }
    }
    throw StateError('蓝牙设备与 USB 控制板身份不一致，未建立控制连接');
  }

  Future<void> _start({bool allowConsent = true, bool restoreLocal = false}) {
    if (_startFuture != null) return _startFuture!;
    final future =
        _performStart(allowConsent: allowConsent, restoreLocal: restoreLocal);
    _startFuture = future;
    return future.whenComplete(() {
      _startFuture = null;
    });
  }

  Future<void> _performStart(
      {bool allowConsent = true, bool restoreLocal = false}) async {
    if (_busy || _stopping || !widget.isCurrent()) return;
    _manuallyStopped.remove(widget.attachment.serial);
    final generation = ++_generation;
    _checkErrors.reset(generation);
    setState(() {
      _busy = true;
      _error = null;
      _code = null;
      _relay = '正在核验控制板';
    });
    try {
      await TargetSession.cancelRecovery();
      if (!_current(generation)) return;
      final identity = await _usbIdentity();
      if (!_current(generation)) return;
      var freshCapture = false;
      if (!await ScreenShare.isActive()) {
        if (!allowConsent) throw StateError('屏幕共享已结束，请主动开始共享');
        await ScreenShare.startUsb(widget.attachment,
            isCurrent: () => _current(generation));
        freshCapture = true;
      }
      final until = DateTime.now().add(const Duration(seconds: 5));
      while (_current(generation) &&
          !await ScreenShare.isActive() &&
          DateTime.now().isBefore(until)) {
        await Future<void>.delayed(const Duration(milliseconds: 100));
      }
      if (!_current(generation)) return;
      _active = await ScreenShare.isActive();
      if (!_current(generation)) return;
      if (!_active) throw StateError('屏幕共享尚未启动，请重试');
      if (freshCapture) {
        TargetSession.noteCapture(widget.attachment, _captureNow);
      } else {
        // Reopening a page does not renew the native capture credential.
        await TargetSession.maintainCapture(widget.attachment,
            clock: widget.captureClock, renew: widget.renewCapture);
        if (!_current(generation)) return;
      }
      setState(() {
        _capture = '正在共享整个屏幕';
        _relay = '正在连接云端中继';
      });
      if (!_externalGateway || restoreLocal) {
        await _connectBoard(identity, generation);
        if (!_current(generation)) return;
        if (restoreLocal) {
          if (_control?.authorized != true) {
            throw StateError('本机中转尚未连接，请重试；其他网关不会被强制接管');
          }
          _externalGateway = false;
        }
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
    _checkErrors.reset(_generation);
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
      await TargetSession.release();
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
    _checkErrors.reset(_generation);
    _timer?.cancel();
    TargetSession.removeView(this);
    if (!TargetSession.owns(_control)) {
      unawaited(_control?.shutdown() ?? Future<void>.value());
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final connected = _control?.authorized == true;
    final ready =
        _active && (connected || _externalGateway) && widget.isCurrent();
    return Scaffold(
      appBar: AppBar(title: const Text('被控手机'), actions: [
        IconButton(
            tooltip: '设置',
            onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(
                builder: (_) => ProductSettingsScreen(
                    client: _control, diagnostic: _relay))),
            icon: const Icon(Icons.settings_outlined))
      ]),
      body: ListView(padding: const EdgeInsets.all(20), children: [
        Text(
            _active
                ? '屏幕共享中'
                : _busy
                    ? '正在连接'
                    : '需要连接',
            style: Theme.of(context).textTheme.headlineMedium),
        const SizedBox(height: 8),
        const Text('接收控制手机或 AI 助手的任务，由控制板执行操作。'),
        const SizedBox(height: 20),
        TargetStatusOverview(
          board: widget.isCurrent() ? '已识别控制板' : '连接已改变，请重新检查连接线',
          capture: productError(_capture),
          permission:
              _pointerReady ? '最近回执允许操作，开始执行前仍会检查' : '执行任务时检查操作许可，空闲无需重复授权',
          network: connected
              ? '此手机中转连接已建立，云端执行状态按任务回执更新'
              : _externalGateway
                  ? '等待控制板直连或另一台手机中转；当前网络状态待更新'
                  : '正在检查手机中转连接',
          error: _error,
        ),
        for (final message in _checkErrors.messages) ProductError(message),
        Card(
            child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('最近任务反馈',
                          style: Theme.of(context).textTheme.titleMedium),
                      const SizedBox(height: 8),
                      Text(_feedback.state.isEmpty
                          ? '任务状态暂未更新，请在控制手机查看最近结果。'
                          : _feedback.taskLabel),
                      if (_feedback.reply.isNotEmpty)
                        Text(productError(_feedback.reply)),
                      const Text('此处显示最近收到的反馈；若与你的任务不一致，请以控制手机的任务页为准。'),
                    ]))),
        const SizedBox(height: 16),
        if (!ready)
          FilledButton.icon(
              onPressed:
                  _busy || _stopping || !widget.isCurrent() ? null : _start,
              icon: const Icon(Icons.link),
              label: Text(_busy
                  ? '正在请求授权或连接…'
                  : _active
                      ? '重新检查手机中转'
                      : '开始屏幕共享并连接')),
        if (_externalGateway && _active)
          OutlinedButton.icon(
              onPressed: _busy || _stopping || !widget.isCurrent()
                  ? null
                  : () => _start(allowConsent: false, restoreLocal: true),
              icon: const Icon(Icons.bluetooth_connected),
              label: const Text('恢复本机手机中转')),
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
                        await TargetSession.release();
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
              label: const Text('释放手机中转，保留屏幕共享')),
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
        const Text(
            '画面用于理解任务和核验结果。返回或进入设置不会停止共享；仅主动停止、系统停止或真实断开连接后，才需要重新开始共享。旧操作不会重放。'),
      ]),
      bottomNavigationBar: SafeArea(
          child: Padding(
              padding: const EdgeInsets.all(16),
              child: OutlinedButton.icon(
                  style: OutlinedButton.styleFrom(
                      foregroundColor: Theme.of(context).colorScheme.error,
                      side: BorderSide(
                          color: Theme.of(context).colorScheme.error)),
                  onPressed: _stopping ? null : _stop,
                  icon: const Icon(Icons.stop_circle_outlined),
                  label: Text(_stopping ? '正在停止…' : '停止控制与共享')))),
    );
  }
}
