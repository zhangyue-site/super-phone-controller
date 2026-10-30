import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:pcflash/ble_ota_service.dart';
import 'package:pcflash/control_client.dart';
import 'package:pcflash/screen_share.dart';
import 'package:pcflash/target_session.dart';
import 'package:pcflash/usb_launch.dart';
import 'package:pcflash/usb_target_screen.dart';

class LocalOwner extends ControlClient {
  bool live = true;
  @override
  bool get authorized => live;
  @override
  bool get canReadStatus => live;
  @override
  Future<void> shutdown() async {
    live = false;
  }
}

class RestoreBoard extends BleOtaService {
  int scans = 0;
  @override
  Stream<List<ScanResult>> get scanResults => const Stream.empty();
  @override
  Future<void> startScan() async {
    scans++;
    throw StateError('gateway conflict denied');
  }

  @override
  Future<void> stopScan() async {}
  @override
  Future<void> disconnect() async {}
}

void main() {
  for (final scenario in ['conflict', 'retained-success', 'stop-pending']) {
    testWidgets(
        'explicit local gateway restore $scenario preserves projection and guards races',
        (tester) async {
      tester.view.physicalSize = const Size(1000, 2400);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      const serial = 'AABBCCDDEE44';
      final usb = UsbAttachment(serial, 'restore:$scenario', null, null);
      final board = RestoreBoard(), old = LocalOwner(), next = LocalOwner();
      final identity = Completer<Map<String, dynamic>>();
      var infos = 0, starts = 0, stops = 0, active = true;
      final messenger =
          TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
      Map<String, dynamic> info() =>
          {'protocol': 1, 'device': 'test-board', 'usbSerial': serial};
      messenger.setMockMethodCallHandler(UsbLaunch.channel, (call) async {
        if (call.method == 'info') {
          infos++;
          if (infos == 2) {
            return identity.future;
          }
          return info();
        }
        return null;
      });
      messenger.setMockMethodCallHandler(ScreenShare.channel, (call) async {
        if (call.method == 'start') starts++;
        if (call.method == 'stop') {
          stops++;
          active = false;
          return null;
        }
        if (call.method == 'captureSession') {
          return {
            'serial': serial,
            'generation': 1,
            'needsAuthorization': false
          };
        }
        if (call.method == 'usbWindow') return '{"state":"idle"}';
        return jsonEncode({'active': active, 'capture': '共享中', 'task': ''});
      });
      addTearDown(() async {
        await TargetSession.release();
        messenger.setMockMethodCallHandler(UsbLaunch.channel, null);
        messenger.setMockMethodCallHandler(ScreenShare.channel, null);
      });
      TargetSession.retain(usb, old, board);
      await tester.pumpWidget(MaterialApp(
          home: UsbTargetScreen(
        attachment: usb,
        service: board,
        isCurrent: () => true,
        renewCapture: (_) async {},
      )));
      await tester.pumpAndSettle();
      expect(board.scans, 0);
      await tester.tap(find.text('释放手机中转，保留屏幕共享'));
      await tester.pumpAndSettle();
      expect(find.text('恢复本机手机中转'), findsOneWidget);
      expect(board.scans, 0, reason: 'release never auto-reclaims the gateway');
      if (scenario == 'retained-success') {
        TargetSession.retain(usb, next, board);
      }
      await tester.tap(find.text('恢复本机手机中转'));
      await tester.tap(find.text('恢复本机手机中转'));
      await tester.pumpAndSettle();
      expect(infos, 2, reason: 'repeated clicks share one in-flight request');
      if (scenario == 'retained-success') {
        identity.complete(info());
        await tester.runAsync(
            () => Future<void>.delayed(const Duration(milliseconds: 20)));
        await tester.pump(const Duration(milliseconds: 100));
        await tester.pumpAndSettle();
        expect(find.text('恢复本机手机中转'), findsNothing);
        expect(find.text('释放手机中转，保留屏幕共享'), findsOneWidget);
        expect(next.live, true);
      } else if (scenario == 'stop-pending') {
        await tester.tap(find.text('停止控制与共享'));
        await tester.pump();
        identity.complete(info());
        await tester.runAsync(
            () => Future<void>.delayed(const Duration(milliseconds: 20)));
        await tester.pump(const Duration(milliseconds: 100));
        await tester.pumpAndSettle();
        expect(board.scans, 0,
            reason: 'late identity must not reconnect after STOP');
        expect(find.text('恢复本机手机中转'), findsNothing);
        expect(stops, 1);
      } else {
        identity.complete(info());
        await tester.runAsync(
            () => Future<void>.delayed(const Duration(milliseconds: 20)));
        await tester.pump(const Duration(milliseconds: 100));
        await tester.pumpAndSettle();
        expect(board.scans, 1);
        for (var i = 0;
            i < 20 &&
                find
                    .textContaining('gateway conflict denied')
                    .evaluate()
                    .isEmpty;
            i++) {
          await tester.pump(const Duration(milliseconds: 50));
        }
        expect(find.textContaining('gateway conflict denied'), findsOneWidget);
        final button = tester.widget<OutlinedButton>(find.ancestor(
            of: find.text('恢复本机手机中转'),
            matching:
                find.byWidgetPredicate((widget) => widget is OutlinedButton)));
        expect(button.onPressed, isNotNull,
            reason: 'conflict keeps explicit retry reachable');
      }
      expect(starts, 0,
          reason: 'restore cannot request MediaProjection permission');
      if (scenario != 'stop-pending') expect(stops, 0);
      await tester.pumpWidget(const SizedBox());
    });
  }
}
