import 'gateway_recovery.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'diagnostics.dart';
import 'dart:async';
import 'dart:convert';
import 'ble_ota_service.dart';
import 'control_client.dart';
import 'screen_share.dart';
import 'usb_launch.dart';

/// App-owned maintenance; observing a page never owns the projection grant.
class TargetSession {
  static Timer? _timer;
  static final _recovery = GatewayRecoveryGate();
  static bool _busy = false;
  static final Set<Object> _views = {};
  static final Map<String, bool> _preparedModes = {};
  static UsbAttachment? _usb;
  static ControlClient? _client;
  static BleOtaService? _service;
  static final Map<String, Future<void>> _windows = {};
  static final Map<String, Future<bool>> _captures = {};
  static final Map<String, DateTime> _captureRenewed = {};
  static void noteCapture(UsbAttachment usb, DateTime now) =>
      _captureRenewed[usb.session] = now;
  static Future<bool> maintainCapture(UsbAttachment usb,
      {DateTime Function()? clock,
      Future<void> Function(UsbAttachment)? renew}) {
    return _captures.putIfAbsent(
        usb.session,
        () =>
            _maintainCapture(usb, clock: clock, renew: renew).whenComplete(() {
              _captures.remove(usb.session);
            }));
  }

  static Future<bool> _maintainCapture(UsbAttachment usb,
      {DateTime Function()? clock,
      Future<void> Function(UsbAttachment)? renew}) async {
    final now = clock?.call() ?? DateTime.now();
    final recovered = await ScreenShare.recoverUsb(usb);
    final previous = _captureRenewed[usb.session];
    if (recovered) {
      _captureRenewed[usb.session] = now;
    } else if (previous == null || now.difference(previous).inSeconds >= 60) {
      await (renew ?? ScreenShare.renewUsb)(usb);
      _captureRenewed[usb.session] = now;
    }
    return recovered;
  }

  static void addView(Object view) => _views.add(view);
  static void removeView(Object view) => _views.remove(view);
  static void startPolling() =>
      _timer ??= Timer.periodic(const Duration(seconds: 2), (_) => maintain());
  static void stopPolling() {
    _timer?.cancel();
    _timer = null;
  }

  static ControlClient? clientFor(UsbAttachment usb) =>
      _usb?.session == usb.session ? _client : null;
  static bool owns(ControlClient? client) =>
      client != null && identical(_client, client);
  static bool get hasGateway => _client?.authorized == true;
  static void retain(
      UsbAttachment usb, ControlClient client, BleOtaService service) {
    _recovery.reset();
    _usb = usb;
    _client = client;
    _service = service;
  }

  static Future<void> release({String diagnosticReason = 'explicit'}) async {
    if (_client != null || _service != null) {
      SafeDiagnostics.record('target_release',
          phase: 'shutdown', reason: diagnosticReason);
    }
    final client = _client, service = _service;
    _client = null;
    _service = null;
    _usb = null;
    _preparedModes.clear();
    final cancelled = _recovery.cancel();
    await client?.shutdown();
    await cancelled;
    await service?.disconnect();
  }

  static bool get hasRetainedOwner => _client != null || _service != null;

  /// A retained owner for a previous USB session never survives a new one.
  static Future<void> releaseStale(UsbAttachment usb) async {
    if (_usb != null && _usb!.session != usb.session) {
      await release(diagnosticReason: 'usb_unavailable');
    }
  }

  static Future<void> cancelRecovery() => _recovery.cancel();
  static void resumeRecovery(ControlClient client) {
    if (identical(_client, client) && client.authorized) _recovery.reset();
  }

  static String get recoveryStatus =>
      _client?.gatewayRecoveryNeedsPairing == true
          ? '授权已过期，请重新连接并配对控制手机'
          : _recovery.status;
  static Future<bool> maintainGateway(UsbAttachment usb) async {
    final client = _client, service = _service;
    if (client == null ||
        service == null ||
        _usb?.session != usb.session ||
        !client.canRecoverGateway) {
      return false;
    }
    final bound = await UsbLaunch.snapshot();
    final remote = bound?.remoteId;
    Future<bool> guard() async {
      if (!identical(_client, client) ||
          _usb?.session != usb.session ||
          !client.canReadStatus) {
        return false;
      }
      final current = await UsbLaunch.snapshot();
      return identical(_client, client) &&
          current?.session == usb.session &&
          current?.serial == usb.serial &&
          remote != null &&
          current?.remoteId == remote &&
          current?.deviceId == client.deviceId &&
          await ScreenShare.isActive();
    }

    return _recovery.tick(
      eligible: () => identical(_client, client) && client.canRecoverGateway,
      guard: guard,
      run: (check) => client.recoverGateway(
          check: check,
          reconnect: () async {
            await check();
            try {
              await service.connect(BluetoothDevice.fromId(remote!));
            } on FlutterBluePlusException catch (error) {
              // Android 133 and the plugin timeout both report "connect";
              // connect() already disconnected the failed attempt.
              if (error.function == 'connect') {
                throw BleReconnectFailure(error);
              }
              rethrow;
            }
            await check();
          }),
    );
  }

  static Future<void> Function(bool) modeCallback(UsbAttachment usb) =>
      (hid) async {
        final current = await UsbLaunch.snapshot();
        if (current?.session != usb.session || !await ScreenShare.isActive()) {
          throw StateError('共享或控制板连接已结束');
        }
        final prepared = _preparedModes.remove(usb.session);
        if (prepared == hid) {
          return;
        }
        await UsbLaunch.channel.invokeMethod<void>(
            'expectMode', {'session': usb.session, 'hid': hid});
      };
  static Future<void> window(UsbAttachment usb) => _windows.putIfAbsent(
      usb.session,
      () => _window(usb).whenComplete(() {
            _windows.remove(usb.session);
          }));
  static Future<void> _window(UsbAttachment usb) async {
    void
        check() {} // Native validates the physical session before/after each request.
    Future<Map<String, dynamic>> request(Map<String, dynamic> body) async {
      check();
      final raw = await ScreenShare.channel.invokeMethod<String>(
          'usbWindow', {'usbSession': usb.session, 'body': jsonEncode(body)});
      check();
      final value = jsonDecode(raw ?? '{}');
      if (value is! Map<String, dynamic>) {
        throw const FormatException('连接检查响应无效');
      }
      return value;
    }

    final state = await request({'operation': 'poll'});
    if (state['state'] == 'idle' || state['state'] == 'ready') return;
    final nonce = state['nonce'],
        mode = state['mode'],
        generation = state['generation'],
        ttl = state['expiresInMs'];
    if (state['state'] != 'prepare' ||
        nonce is! String ||
        !RegExp(r'^[0-9a-f]{32}$').hasMatch(nonce) ||
        (mode != 'hid' && mode != 'normal') ||
        generation is! int ||
        ttl is! int ||
        ttl < 1 ||
        ttl > 5000) {
      throw const FormatException('连接检查已失效');
    }
    await UsbLaunch.channel.invokeMethod<void>(
        'expectMode', {'session': usb.session, 'hid': mode == 'hid'});
    check();
    _preparedModes[usb.session] = mode == 'hid';
    final result = await request({
      'operation': 'ready',
      'nonce': nonce,
      'mode': mode,
      'generation': generation
    });
    if (result['state'] != 'ready') throw StateError('连接切换尚未确认');
  }

  static Future<void> maintain() async {
    if (_busy || _views.isNotEmpty) return;
    _busy = true;
    try {
      final usb = await UsbLaunch.snapshot();
      if (usb == null || (_usb != null && _usb!.session != usb.session)) {
        await release(diagnosticReason: 'usb_unavailable');
        return;
      }
      if (!await ScreenShare.isActive()) {
        await release(diagnosticReason: 'capture_inactive');
        return;
      }
      try {
        await maintainCapture(usb);
      } catch (_) {/* Native projection remains alive; next tick retries. */}
      try {
        await window(usb);
      } catch (_) {/* Independent from capture credentials. */}
      try {
        await _client?.refresh();
      } catch (_) {/* Never recreate a projection. */}
      await maintainGateway(usb);
    } catch (_) {
      /* Keep native service ownership during short failures. */
    } finally {
      _busy = false;
    }
  }
}
