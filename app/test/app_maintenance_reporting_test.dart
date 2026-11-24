import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:pcflash/app_maintenance.dart';
import 'package:pcflash/app_maintenance_widgets.dart';
import 'package:pcflash/ble_ota_service.dart';
import 'package:pcflash/control_client.dart';
import 'package:pcflash/diagnostics.dart';
import 'package:pcflash/target_session.dart';
import 'package:pcflash/usb_launch.dart';
import 'control_client_test.dart' show FakeBoard;

class TargetObserver extends ControlClient {
  final reports = <Map<String, Object?>>[];
  Map<String, dynamic>? remote;
  @override
  bool get canReadStatus => true;
  @override
  bool get canReportAppMaintenance => true;
  @override
  Future<void> reportAppMaintenance(Map<String, Object?> data) async =>
      reports.add(data);
  @override
  Future<Map<String, dynamic>?> readAppMaintenance() async => remote;
  @override
  Future<void> shutdown() async {}
}

class PassiveBoard extends BleOtaService {
  @override
  Future<void> disconnect() async {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test(
      'authenticated observation sends only allowlisted data and an old server cannot end a control lease',
      () async {
    final calls = <http.Request>[];
    final client = ControlClient(client: MockClient((r) async {
      calls.add(r);
      final name = r.url.pathSegments.last;
      return switch (name) {
        'challenge' => http.Response(jsonEncode({'challenge': 'a' * 64}), 200),
        'authorize' => http.Response(
            jsonEncode({
              'scope': 'phone-commands',
              'ticket': 't' * 43,
              'expiresIn': 300
            }),
            200),
        'maintenance-read' => http.Response('{"appMaintenance":null}', 200),
        _ => http.Response('{}', 403),
      };
    }));
    expect(await client.readAppMaintenance(), isNull);
    expect(calls, isEmpty);
    await client.authorize(FakeBoard());
    expect(client.canReportAppMaintenance, true);
    await expectLater(
        client.reportAppMaintenance({
          'installedCode': 98,
          'installedName': '1.4.18',
          'state': 'ready',
          'targetCode': 99,
          'sensitive': 'PRIVATE_TEST_SENTINEL',
          'observedAt': 'do not send',
        }),
        throwsA(isA<ControlHttpFailure>()));
    final req = calls.last;
    expect(req.url.path, endsWith('/maintenance-report'));
    expect(jsonDecode(req.body), {
      'installedCode': 98,
      'installedName': '1.4.18',
      'state': 'ready',
      'targetCode': 99
    });
    expect(req.headers['Authorization'], 'Bearer ${'t' * 43}');
    expect(client.authorized, true);
    expect(await client.readAppMaintenance(), isNull);
    expect(calls.last.body, '{}');
    await client.shutdown();
  });

  testWidgets(
      'only a bound target session reports, coalescing equal states and refusing a replaced USB board',
      (t) async {
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    const native = MethodChannel('pcflash/update');
    const attachment = UsbAttachment(
        'ABCDEF012345', 'ABCDEF012345:1', 'AB:CD:EF:01:23:45', 'board-a');
    String bound = 'board-a', state = 'current';
    messenger.setMockMethodCallHandler(
        UsbLaunch.channel,
        (c) async => {
              'serial': attachment.serial,
              'session': attachment.session,
              'remoteId': attachment.remoteId,
              'deviceId': bound,
            });
    messenger.setMockMethodCallHandler(
        native,
        (c) async => {
              'state': c.method == 'status' ? 'idle' : state,
              'installedCode': 98,
              'installedName': '1.4.18',
              'versionCode': state == 'current' ? 98 : 99,
              'versionName': '1.4.19',
            });
    final client = TargetObserver()..deviceId = 'board-a';
    final view = Object();
    TargetSession.addView(view);
    AppMaintenance.shared.setForeground(true);
    await t.pump();
    TargetSession.startPolling();
    expect(client.reports, isEmpty);
    TargetSession.retain(attachment, client, PassiveBoard());
    await t.pump();
    expect(client.reports.last['state'], 'current');
    final count = client.reports.length;
    await t.pump(const Duration(seconds: 4));
    expect(client.reports.length, count);
    state = 'ready';
    await AppMaintenance.shared.check();
    await t.pump();
    expect(client.reports.last['state'], 'ready');
    final accepted = client.reports.length;
    bound = 'different-board';
    state = 'current';
    await AppMaintenance.shared.check();
    await t.pump();
    expect(client.reports.length, accepted);
    TargetSession.stopPolling();
    TargetSession.removeView(view);
    await TargetSession.release();
    AppMaintenance.shared.setForeground(false);
    messenger.setMockMethodCallHandler(UsbLaunch.channel, null);
    messenger.setMockMethodCallHandler(native, null);
  });

  testWidgets(
      'controller displays server reception time and does not reuse another device record',
      (t) async {
    final client = TargetObserver()
      ..deviceId = 'board-a'
      ..remote = {
        'installedCode': 98,
        'installedName': '1.4.18',
        'state': 'ready',
        'targetCode': 99,
        'receivedAt': '2026-11-24T08:00:00Z',
        'ageSeconds': 200,
      };
    await t.pumpWidget(MaterialApp(
        home: Scaffold(body: RemoteMaintenanceCard(client: client))));
    await t.pumpAndSettle();
    expect(find.textContaining('已装 1.4.18（98）'), findsOneWidget);
    expect(find.textContaining('上报已过期'), findsOneWidget);
    client.deviceId = 'board-b';
    client.remote = null;
    await t.tap(find.byTooltip('刷新被控手机维护状态'));
    await t.pumpAndSettle();
    expect(find.textContaining('已装 1.4.18（98）'), findsNothing);
    expect(find.textContaining('尚无被控手机上报'), findsOneWidget);
    await t.pumpWidget(const SizedBox());
  });
}
