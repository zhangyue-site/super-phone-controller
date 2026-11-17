import 'accessibility_assist.dart';
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
import 'target_progress_card.dart';
import 'local_auto_loop.dart';
import 'overlay_pill.dart';

/// The target owns capture and USB authorization; Bluetooth relay is optional.
class UsbTargetScreen extends StatefulWidget {
  final UsbAttachment attachment;
  final BleOtaService? service;
  final ControlClient Function()? createControlClient;
  final VoidCallback? onLegacy;
  final bool Function() isCurrent;
  final DateTime Function()? captureClock;
  final Future<void> Function(UsbAttachment)? renewCapture;
  const UsbTargetScreen(
      {super.key,
      required this.attachment,
      required this.isCurrent,
      this.service,
      this.createControlClient,
      this.onLegacy,
      this.captureClock,
      this.renewCapture});
  @override
  State<UsbTargetScreen> createState() => _UsbTargetScreenState();
}

class _UsbTargetScreenState extends State<UsbTargetScreen> {
  static final Map<String, String> _stopNotes = {};
  static final Set<String> _manuallyStopped = <String>{};
  static final Set<String> _autoAttemptedSessions = <String>{};
  Timer? _timer;
  ControlClient? _control;
  Future<void>? _startFuture;
  bool _busy = false, _active = false, _polling = false, _stopping = false;
  bool _pointerReady = false, _lost = false, _externalGateway = false;
  bool _boardVerified = false, _bluetoothRequested = false;
  int _generation = 0;
  int? _captureStartErrorGeneration;
  String? _captureStartErrorMessage;
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
    _error = _stopNotes[widget.attachment.session];
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
            _boardVerified = false;
            _relay = 'USB 已断开，本机控制授权已关闭';
            _error = _control?.usbRevokeFailed == true
                ? '云端撤销未确认；本机已结束授权，旧动作不会重发'
                : null;
          });
        }
        return;
      }
      // While any page is open the background maintain() never runs, so a
      // re-enumerated USB session releases the previous owner here.
      await TargetSession.releaseStale(widget.attachment);
      if (!_current(generation)) return;
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
            setState(() {
              _checkErrors.succeed(TargetCheckPhase.capture, generation);
              if (_captureStartErrorGeneration == generation &&
                  _error == _captureStartErrorMessage) {
                _error = null;
                _captureStartErrorGeneration = null;
                _captureStartErrorMessage = null;
              }
            });
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

  Future<void> _switchTransport(bool bluetooth) async {
    if (_busy || _stopping || !_active || !widget.isCurrent()) return;
    final generation = ++_generation;
    setState(() {
      _busy = true;
      _error = null;
      _code = null;
    });
    try {
      final previous = _control;
      await TargetSession.release(diagnosticReason: 'transport_switch');
      await previous?.shutdown();
      if (!_current(generation)) return;
      if (previous?.usbRevokeFailed == true) {
        throw StateError('云端撤销未确认，请先检查连接；不会切换或重放旧任务');
      }
      _control = null;
      _bluetoothRequested = bluetooth;
      _externalGateway = false;
    } catch (e) {
      if (_current(generation)) setState(() => _error = '连接切换未完成：$e');
      return;
    } finally {
      if (mounted && generation == _generation) setState(() => _busy = false);
    }
    if (_current(generation)) await _start(allowConsent: false);
  }

  Future<void> _connectBoard(String identity, int generation) async {
    final owner = TargetSession.clientFor(widget.attachment);
    if (owner?.authorized == true) {
      TargetSession.resumeRecovery(owner!);
      _control = owner;
      _bluetoothRequested = !owner.usesUsbDirect;
      _relay = owner.usesUsbDirect ? 'USB 授权已建立；等待板端 Wi-Fi 与任务回执' : '手机中转连接已保留';
      return;
    }
    if (!_bluetoothRequested) {
      if (TargetSession.hasRetainedOwner) {
        await TargetSession.release(diagnosticReason: 'usb_reauthorize');
      }
      if (!_current(generation)) return;
      await _control?.shutdown();
      if (!_current(generation)) return;
      final client = widget.createControlClient?.call() ?? ControlClient();
      _control = client;
      await client.authorizeUsb(widget.attachment,
          isCurrent: () => _current(generation));
      if (!_current(generation)) {
        await client.shutdown();
        return;
      }
      if (client.deviceId != null && client.deviceId != identity) {
        await client.shutdown();
        throw StateError('USB控制授权目标已改变');
      }
      TargetSession.retain(widget.attachment, client, null);
      _relay = 'USB 授权已建立；等待板端 Wi-Fi 与任务回执';
      return;
    }
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
    // Same cleanup as "释放手机中转": an unauthorized retained owner, possibly
    // on another BleOtaService instance, and any link left on this service
    // would keep the single-connection board from advertising.
    if (TargetSession.hasRetainedOwner) {
      await TargetSession.release(diagnosticReason: 'owner_shutdown');
    }
    await _control?.shutdown();
    await service.disconnect();
    if (!_current(generation)) return;
    final devices = <String, BluetoothDevice>{};
    final bound = widget.attachment.remoteId;
    final scanFrom = DateTime.now();
    final sub = service.scanResults.listen((results) {
      for (final result in results) {
        // scanResults re-emits the previous scan to a new listener; only
        // advertisements seen by this scan prove the board is reachable.
        if (result.timeStamp.isBefore(scanFrom)) continue;
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
    _stopNotes.remove(widget.attachment.session);
    final generation = ++_generation;
    _captureStartErrorGeneration = null;
    _captureStartErrorMessage = null;
    var captureStage = false;
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
      await TargetSession.releaseStale(widget.attachment);
      if (!_current(generation)) return;
      final identity = await _usbIdentity();
      if (!_current(generation)) return;
      setState(() => _boardVerified = true);
      captureStage = true;
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
      captureStage = false;
      if (restoreLocal) _bluetoothRequested = true;
      setState(() {
        _capture = '正在共享整个屏幕';
        _relay = _bluetoothRequested ? '正在连接蓝牙备用中转' : '正在通过 USB 核验控制授权';
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
      if (_current(generation) &&
          _control?.authorized == true &&
          _code == null) {
        final pairing = await _control!.pairingCode();
        final code = pairing['code'];
        if (_current(generation) &&
            code is String &&
            RegExp(r'^\d{4}$').hasMatch(code) &&
            pairing['persistent'] == true) {
          setState(() {
            _code = code;
            _codeExpiry = null;
          });
        }
      }
    } catch (e) {
      workbenchDiagnostic('relay_error',
          value: e is MissingPluginException
              ? 1
              : e is TimeoutException
                  ? 2
                  : 3);
      if (_current(generation)) {
        setState(() {
          _error = '连接未完成：$e';
          _captureStartErrorGeneration = captureStage ? generation : null;
          _captureStartErrorMessage = captureStage ? _error : null;
        });
      }
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
          !(RegExp(r'^\d{4}$').hasMatch(code) &&
                  result['persistent'] == true) &&
              !(RegExp(r'^[A-Za-z0-9_-]{43}$').hasMatch(code) &&
                  result['expiresIn'] == 120)) {
        throw StateError('绑定码无效');
      }
      if (_current(generation)) {
        setState(() {
          _code = code;
          _codeExpiry = result['persistent'] == true
              ? null
              : DateTime.now().add(const Duration(seconds: 120));
        });
      }
    } catch (e) {
      if (_current(generation)) setState(() => _error = '无法生成连接码：$e');
    } finally {
      if (mounted && generation == _generation) setState(() => _busy = false);
    }
  }

  Future<void> _manageBinding({required bool rotate}) async {
    final confirmed = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
                title: Text(rotate ? '更换绑定码？' : '解除控制手机？'),
                content: Text(rotate
                    ? '旧绑定码将失效，已连接的控制手机将被解除。屏幕共享继续保留。'
                    : '当前控制手机将被解除；绑定码保持有效，可重新连接。屏幕共享继续保留。'),
                actions: [
                  TextButton(
                      onPressed: () => Navigator.pop(context, false),
                      child: const Text('取消')),
                  FilledButton(
                      onPressed: () => Navigator.pop(context, true),
                      child: const Text('确认'))
                ]));
    if (confirmed != true || !mounted || _control?.authorized != true) return;
    final generation = _generation;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      if (rotate) {
        final result = await _control!.rotatePairingCode();
        final code = result['code'];
        if (code is! String ||
            !RegExp(r'^\d{4}$').hasMatch(code) ||
            result['persistent'] != true) {
          throw StateError('绑定码未确认，请重新检查');
        }
        if (_current(generation)) {
          setState(() {
            _code = code;
            _codeExpiry = null;
          });
        }
      } else {
        await _control!.revokeControllers();
      }
    } catch (e) {
      if (_current(generation)) setState(() => _error = '绑定管理未完成：$e');
    } finally {
      if (mounted && generation == _generation) setState(() => _busy = false);
    }
  }

  Future<void> _rotateCode() => _manageBinding(rotate: true);
  Future<void> _revokeBindings() => _manageBinding(rotate: false);

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
      if (_control?.usbRevokeFailed == true) {
        failure = '云端撤销未确认，请检查网络；设备停止仍待核验。';
      }
      await widget.service?.disconnect();
      if (mounted) {
        setState(() {
          _active = false;
          _pointerReady = false;
          _busy = false;
          _stopping = false;
          _capture = failure == null ? '本机共享停止请求已完成' : '共享停止状态待确认';
          _relay = '本机连接已关闭；云端任务停止仍需核验';
          _error = failure ?? '本机停止请求已完成；云端任务停止与已发动作结果仍需确认。';
          _stopNotes[widget.attachment.session] = _error!;
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
                builder: (_) => Scaffold(
                    body: ProductSettingsScreen(
                        client: _control, diagnostic: _relay),
                    bottomNavigationBar: SafeArea(
                        child: Padding(
                            padding: const EdgeInsets.all(16),
                            child: OutlinedButton.icon(
                                onPressed: _stop,
                                icon: const Icon(Icons.stop_circle_outlined),
                                label: const Text('停止控制与共享'))))))),
            icon: const Icon(Icons.settings_outlined))
      ]),
      body: ListView(padding: const EdgeInsets.all(20), children: [
        Text(
            ready && !_feedback.isCloudStale(DateTime.now())
                ? (_control?.usesUsbDirect == true
                    ? 'USB 已授权，等待板端连接'
                    : '已连接，等待或接收任务')
                : _active
                    ? '整屏共享中，正在检查连接'
                    : _busy
                        ? '正在连接'
                        : '需要连接',
            style: Theme.of(context).textTheme.headlineMedium),
        const SizedBox(height: 8),
        const Text('USB 连接并授权、共享整屏，再在控制手机输入绑定码。板子通过 Wi-Fi 连接云端，蓝牙中转为可选备用。'),
        if (!ready)
          Card(
              child: Padding(
                  padding: const EdgeInsets.all(20),
                  child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(_error != null ? '恢复后，重新检查' : '首次连接 · 三步准备',
                            style: Theme.of(context).textTheme.titleMedium),
                        const SizedBox(height: 12),
                        const Text(
                            '1  检查控制板与 USB 连接\n\n2  允许系统的整屏共享\n\n3  在控制手机输入绑定码'),
                        if (_error != null)
                          const Padding(
                              padding: EdgeInsets.only(top: 12),
                              child: Text('先核对连接与最新画面，不自动续跑旧动作。')),
                      ]))),
        const SizedBox(height: 20),
        TargetStatusOverview(
          board: widget.isCurrent()
              ? (_boardVerified ? '控制板身份已核验' : 'USB 已连接，控制板身份待核验')
              : '连接已改变，请重新检查连接线',
          capture: productError(_capture),
          permission:
              _pointerReady ? '最近回执允许操作，开始执行前仍会检查' : '执行任务时检查操作许可，空闲无需重复授权',
          network: connected
              ? (_control?.usesUsbDirect == true
                  ? 'USB 授权已建立；板端 Wi-Fi 在线状态以心跳和任务回执为准'
                  : '此手机中转连接已建立，云端执行状态按任务回执更新')
              : _externalGateway
                  ? '等待控制板直连或另一台手机中转；当前网络状态待更新'
                  : '正在检查 USB 授权与板端直连状态',
          error: _error,
        ),
        for (final message in _checkErrors.messages) ProductError(message),
        TargetProgressCard(
            status: _feedback,
            connected: (connected || _externalGateway) && _active,
            now: DateTime.now()),
        const Card(
            child: ExpansionTile(
                maintainState: true,
                title: Text('本地识别与帮助'),
                subtitle: Text('查看本地 OCR 真实状态与辅助选项'),
                children: [
              AccessibilityAssistCard(),
              OverlayPillCard(),
              Padding(
                  padding: EdgeInsets.fromLTRB(8, 12, 8, 4),
                  child: Text('本地 OCR 与识别 · 状态未返回时保持待确认')),
              LocalAutoLoopCard()
            ])),
        const SizedBox(height: 16),
        if (!ready)
          FilledButton.icon(
              onPressed:
                  _busy || _stopping || !widget.isCurrent() ? null : _start,
              icon: const Icon(Icons.link),
              label: Text(_busy
                  ? '正在请求授权或连接…'
                  : _active
                      ? (_bluetoothRequested ? '重新检查手机中转' : '重新检查控制连接')
                      : '开始屏幕共享并连接')),
        if (_active) const Text('切换连接会结束当前控制任务并保留屏幕共享，旧动作不会重放。'),
        if (_active && !_bluetoothRequested && widget.service != null)
          OutlinedButton.icon(
              onPressed:
                  _busy || _stopping ? null : () => _switchTransport(true),
              icon: const Icon(Icons.bluetooth),
              label: const Text('改用蓝牙中转（备用）')),
        if (_active && _bluetoothRequested && !_externalGateway)
          OutlinedButton.icon(
              onPressed:
                  _busy || _stopping ? null : () => _switchTransport(false),
              icon: const Icon(Icons.usb),
              label: const Text('改用 USB 授权与 Wi-Fi 直连')),
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
        if (!_externalGateway &&
            _control != null &&
            _control?.usesUsbDirect != true)
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
                        TargetBindingCode(
                            code: _code!, persistent: _codeExpiry == null),
                        TextButton.icon(
                            onPressed: () async {
                              try {
                                await Clipboard.setData(
                                    ClipboardData(text: _code!));
                              } catch (_) {
                                if (mounted) {
                                  setState(() => _error = '复制未完成，请长按绑定码手动复制。');
                                }
                              }
                            },
                            icon: const Icon(Icons.copy),
                            label: const Text('复制绑定码')),
                        if (_codeExpiry == null)
                          ExpansionTile(
                              tilePadding: EdgeInsets.zero,
                              title: const Text('管理绑定'),
                              children: [
                                TextButton(
                                    onPressed:
                                        _busy || _stopping ? null : _rotateCode,
                                    child: const Text('更换绑定码并解除控制手机')),
                                TextButton(
                                    onPressed: _busy || _stopping
                                        ? null
                                        : _revokeBindings,
                                    child: const Text('解除控制手机，保留绑定码')),
                              ]),
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
