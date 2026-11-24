import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/app_maintenance.dart';
import 'package:pcflash/app_maintenance_widgets.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const ch = MethodChannel('test/officialAppMaintenance');
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  late AppMaintenance model;
  final methods = <String>[];
  const installed = {'installedCode': 98, 'installedName': '1.4.18'};
  const candidate = {'versionCode': 99, 'versionName': '1.4.19', 'bytes': 1000};
  Map<String, Object> values(String state, {bool newer = true}) => {
        ...installed,
        if (newer) ...candidate,
        'state': state,
      };
  void respond(FutureOr<Object?> Function(String) answer) {
    messenger.setMockMethodCallHandler(ch, (call) async {
      methods.add(call.method);
      if (call.arguments != null) {
        throw StateError('update method used arguments');
      }
      return answer(call.method);
    });
  }

  setUp(() {
    methods.clear();
    model = AppMaintenance(channel: ch);
  });
  tearDown(() {
    model.dispose();
    messenger.setMockMethodCallHandler(ch, null);
  });

  testWidgets('automatic foreground preparation never opens any system UI',
      (t) async {
    final pending = Completer<Object?>();
    var status = 'idle';
    respond((method) => switch (method) {
          'status' => {...values(status), 'received': 500},
          'check' => values('available'),
          'download' => pending.future,
          _ => throw StateError(method),
        });
    model.setForeground(true);
    await t.pump();
    expect(methods, ['status', 'check', 'download']);
    status = 'downloading';
    await t.pump(const Duration(milliseconds: 760));
    await t.pump();
    expect(model.progress, 0.5);
    status = 'verifying';
    await t.pump(const Duration(milliseconds: 760));
    await t.pump();
    expect(model.state, AppUpdateState.verifying);
    pending.complete(values('ready'));
    await t.pump();
    expect(model.state, AppUpdateState.ready);
    expect(model.report, {
      'installedCode': 98,
      'installedName': '1.4.18',
      'state': 'ready',
      'targetCode': 99
    });
    model.setForeground(false);
    model.setForeground(true);
    await t.pump();
    expect(methods.where((m) => m == 'install' || m == 'openInstallSettings'),
        isEmpty);
    expect(methods.where((m) => m == 'download'), hasLength(1));
  });

  testWidgets(
      'known current, offline, and explicit retry use the installed package identity',
      (t) async {
    var offline = true;
    respond((m) {
      if (m == 'status') return values('idle', newer: false);
      if (offline) {
        throw PlatformException(
            code: 'network', message: 'unsafe server string');
      }
      return values('current', newer: false);
    });
    model.setForeground(true);
    await t.pump();
    expect(model.installedLabel, '1.4.18（98）');
    expect(model.state, AppUpdateState.error);
    expect(model.summary, isNot(contains('unsafe')));
    expect(model.report?['state'], 'error');
    offline = false;
    await model.check();
    await t.pump();
    expect(model.state, AppUpdateState.current);
    expect(methods, isNot(contains('download')));
  });

  testWidgets('backgrounding during version lookup defers the first download',
      (t) async {
    final check = Completer<Object?>();
    respond((m) => m == 'status'
        ? values('idle')
        : m == 'check'
            ? check.future
            : values('ready'));
    model.setForeground(true);
    await t.pump();
    model.setForeground(false);
    check.complete(values('available'));
    await t.pump();
    expect(methods, isNot(contains('download')));
    model.setForeground(true);
    await t.pump();
    expect(model.state, AppUpdateState.ready);
    expect(methods.where((m) => m == 'download'), hasLength(1));
  });

  testWidgets(
      'cancellation suppresses late download completion and automatic restart',
      (t) async {
    final pending = Completer<Object?>();
    respond((m) => switch (m) {
          'status' => values('idle'),
          'check' => values('available'),
          'download' => pending.future,
          'cancel' => values('cancelled'),
          _ => throw StateError(m)
        });
    model.setForeground(true);
    await t.pump();
    await model.cancel();
    pending.complete(values('ready'));
    await t.pump();
    expect(model.state, AppUpdateState.available);
    model.setForeground(false);
    model.setForeground(true);
    await t.pump();
    expect(methods.where((m) => m == 'download'), hasLength(1));
  });

  testWidgets(
      'explicit install, source permission, and return from installer never imply installed',
      (t) async {
    bool allowed = false;
    respond((m) => switch (m) {
          'status' => values('idle'),
          'check' => values('ready'),
          'install' => values(allowed ? 'launched' : 'permission_required'),
          'openInstallSettings' => values('settings_opened'),
          _ => throw StateError(m),
        });
    model.setForeground(true);
    await t.pump();
    await t.pumpWidget(MaterialApp(
        home: Builder(
            builder: (context) => TextButton(
                onPressed: () => showMaintenance(context, model),
                child: const Text('维护')))));
    await t.tap(find.text('维护'));
    await t.pumpAndSettle();
    expect(find.textContaining('1.4.18（98）'), findsOneWidget);
    expect(methods, isNot(contains('install')));
    await t.tap(find.text('确认安装'));
    await t.pumpAndSettle();
    expect(model.state, AppUpdateState.permissionRequired);
    expect(methods, isNot(contains('openInstallSettings')));
    await t.tap(find.text('打开安装权限设置'));
    await t.pumpAndSettle();
    expect(methods.last, 'openInstallSettings');
    allowed = true;
    model.setForeground(false);
    model.setForeground(true);
    await t.pump();
    await t.tap(find.text('确认安装'));
    await t.pumpAndSettle();
    expect(model.state, AppUpdateState.installerOpened);
    expect(model.report?['installedCode'], 98);
    expect(find.textContaining('等待核对安装结果'), findsOneWidget);
    model.setForeground(false);
    model.setForeground(true);
    await t.pump();
    expect(model.state, AppUpdateState.ready);
    expect(methods.where((m) => m == 'install'), hasLength(2));
  });
}
