import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

enum AppUpdateState {
  idle,
  checking,
  current,
  available,
  downloading,
  verifying,
  ready,
  permissionRequired,
  installerOpened,
  error
}

class AppMaintenance extends ChangeNotifier {
  AppMaintenance({MethodChannel? channel, DateTime Function()? clock})
      : _channel = channel ?? const MethodChannel('pcflash/update'),
        _clock = clock ?? DateTime.now;

  static final shared = AppMaintenance();
  final MethodChannel _channel;
  final DateTime Function() _clock;
  AppUpdateState state = AppUpdateState.idle;
  String? installedName, targetName;
  int? installedCode, targetCode;
  int received = 0, bytes = 0;
  String errorText = '';
  DateTime? observedAt, _lastCheck;
  bool _foreground = false, _busy = false, _awaitingSystem = false;
  int _revision = 0, _resumeCount = 0;
  int? _cancelledCode;
  Timer? _timer;
  bool _polling = false;

  bool get busy => _busy;
  double? get progress =>
      bytes > 0 ? (received / bytes).clamp(0, 1).toDouble() : null;
  String get installedLabel => installedCode == null || installedName == null
      ? '暂时无法读取'
      : '$installedName（$installedCode）';
  String get targetLabel => targetCode == null || targetName == null
      ? '更新包'
      : '$targetName（$targetCode）';

  String get summary => switch (state) {
        AppUpdateState.idle => '等待检查正式版本',
        AppUpdateState.checking => '正在检查正式版本',
        AppUpdateState.current => '本机已是最新可用版本',
        AppUpdateState.available => '可下载 $targetLabel',
        AppUpdateState.downloading => progress == null
            ? '正在下载更新包'
            : '正在下载更新包 ${(progress! * 100).floor()}%',
        AppUpdateState.verifying => '正在校验更新包',
        AppUpdateState.ready => '$targetLabel 已校验，等待确认安装',
        AppUpdateState.permissionRequired => '请允许此应用安装更新，返回后再次点击安装',
        AppUpdateState.installerOpened => '已打开系统安装界面，等待核对安装结果',
        AppUpdateState.error => errorText,
      };

  /// Snapshot for a target-authenticated status request. System identity is only
  /// populated from PackageManager via the native channel.
  Map<String, Object?>? get report {
    if (installedCode == null || installedName == null || observedAt == null) {
      return null;
    }
    return {
      'installedCode': installedCode!,
      'installedName': installedName!,
      'state': switch (state) {
        AppUpdateState.permissionRequired => 'permission_required',
        AppUpdateState.installerOpened => 'installer_opened',
        _ => state.name,
      },
      if (targetCode != null) 'targetCode': targetCode!,
    };
  }

  void _state(AppUpdateState next) {
    state = next;
    observedAt = _clock().toUtc();
    notifyListeners();
  }

  void setForeground(bool value) {
    if (_foreground == value) return;
    _foreground = value;
    if (value) _resumeCount++;
    if (!value || _busy) return;
    final stale = _lastCheck == null ||
        _clock().difference(_lastCheck!) >= const Duration(minutes: 15);
    if (stale ||
        _awaitingSystem ||
        (state == AppUpdateState.available && targetCode != _cancelledCode)) {
      unawaited(check(manual: false));
    }
  }

  Future<Map<String, Object?>> _call(String method) async {
    final value = await _channel.invokeMapMethod<String, Object?>(method);
    if (value == null) throw const FormatException('missing update response');
    return value;
  }

  void _identity(Map<String, Object?> m) {
    final installed = m['installedCode'], name = m['installedName'];
    if (installed is int &&
        installed > 0 &&
        name is String &&
        name.isNotEmpty &&
        name.length <= 80) {
      installedCode = installed;
      installedName = name;
    }
    final target = m['versionCode'], label = m['versionName'];
    if (target is int && target > 0) targetCode = target;
    if (label is String && label.isNotEmpty && label.length <= 80) {
      targetName = label;
    }
    if (m['received'] case final int n) received = n;
    if (m['bytes'] case final int n) bytes = n;
  }

  void _apply(Map<String, Object?> m) {
    _identity(m);
    final next = switch (m['state']) {
      'idle' => AppUpdateState.idle,
      'checking' => AppUpdateState.checking,
      'current' => AppUpdateState.current,
      'available' || 'cancelled' => AppUpdateState.available,
      'downloading' => AppUpdateState.downloading,
      'verifying' => AppUpdateState.verifying,
      'ready' => AppUpdateState.ready,
      'permission_required' => AppUpdateState.permissionRequired,
      'launched' => AppUpdateState.installerOpened,
      'settings_opened' => AppUpdateState.permissionRequired,
      _ => throw const FormatException('unknown update state'),
    };
    _state(next);
  }

  void _fail(Object error) {
    final code = error is PlatformException ? error.code : '';
    errorText = switch (code) {
      'network' => '未能连接正式下载站，请重试',
      'invalid_release' || 'verification' => '更新包未通过校验，请重新检查',
      'storage' => '存储空间不足或无法保存更新包',
      'foreground' => '请返回应用再试',
      'installer_unavailable' => '系统安装器暂时无法打开',
      'not_ready' => '更新包尚未就绪，请重新检查',
      'busy' => '更新操作仍在进行，请稍后重试',
      _ => '暂时无法获取更新状态，请重试',
    };
    _state(AppUpdateState.error);
  }

  Future<void> check({bool manual = true}) async {
    if (!_foreground || _busy) return;
    _busy = true;
    final revision = ++_revision;
    _lastCheck = _clock();
    _awaitingSystem = false;
    if (manual) _cancelledCode = null;
    _state(AppUpdateState.checking);
    try {
      // status reads the installed identity locally, even while the store is offline.
      final local = await _call('status');
      if (revision != _revision) return;
      _identity(local);
      notifyListeners();
      if (!_foreground) {
        _lastCheck = null;
        _state(AppUpdateState.idle);
        return;
      }
      final result = await _call('check');
      if (revision != _revision) return;
      _apply(result);
      if (_foreground &&
          state == AppUpdateState.available &&
          targetCode != null &&
          targetCode != _cancelledCode) {
        await _download(revision);
      }
    } catch (error) {
      if (revision == _revision) _fail(error);
    } finally {
      if (revision == _revision) {
        _busy = false;
        notifyListeners();
      }
    }
  }

  Future<void> _download(int revision) async {
    received = 0;
    _state(AppUpdateState.downloading);
    _timer?.cancel();
    _timer = Timer.periodic(
        const Duration(milliseconds: 750), (_) => _poll(revision));
    try {
      final result = await _call('download');
      if (revision == _revision) _apply(result);
    } finally {
      if (revision == _revision) {
        _timer?.cancel();
        _timer = null;
      }
    }
  }

  Future<void> _poll(int revision) async {
    if (!_foreground || _polling || revision != _revision) return;
    _polling = true;
    try {
      final m = await _call('status');
      if (revision == _revision &&
          _timer != null &&
          (m['state'] == 'downloading' || m['state'] == 'verifying')) {
        _apply(m);
      }
    } catch (_) {
      // The completion of the download reports its authoritative terminal result.
    } finally {
      _polling = false;
    }
  }

  Future<void> cancel() async {
    if (state != AppUpdateState.downloading &&
        state != AppUpdateState.verifying) {
      return;
    }
    final revision = ++_revision;
    _timer?.cancel();
    _timer = null;
    _cancelledCode = targetCode;
    try {
      final m = await _call('cancel');
      if (revision == _revision) _apply(m);
    } catch (error) {
      if (revision == _revision) _fail(error);
    } finally {
      if (revision == _revision) {
        _busy = false;
        notifyListeners();
      }
    }
  }

  /// Both install methods can only be reached from explicit on-device buttons.
  Future<void> requestInstall() async {
    if (!_foreground ||
        _busy ||
        (state != AppUpdateState.ready &&
            state != AppUpdateState.permissionRequired)) {
      return;
    }
    final method = state == AppUpdateState.permissionRequired
        ? 'openInstallSettings'
        : 'install';
    final revision = ++_revision, resumeBefore = _resumeCount;
    _busy = true;
    notifyListeners();
    try {
      final result = await _call(method);
      if (revision != _revision) return;
      _apply(result);
      _awaitingSystem =
          result['state'] == 'launched' || result['state'] == 'settings_opened';
    } catch (error) {
      if (revision == _revision) _fail(error);
    } finally {
      if (revision == _revision) {
        _busy = false;
        notifyListeners();
        if (_awaitingSystem && _foreground && _resumeCount != resumeBefore) {
          unawaited(check(manual: false));
        }
      }
    }
  }

  @override
  void dispose() {
    ++_revision;
    _timer?.cancel();
    super.dispose();
  }
}
