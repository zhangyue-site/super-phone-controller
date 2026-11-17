import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:pcflash/ble_ota_service.dart';
import 'package:pcflash/control_client.dart';
import 'package:pcflash/screen_share.dart';
import 'package:pcflash/product_widgets.dart';
import 'package:pcflash/target_session.dart';
import 'package:pcflash/usb_launch.dart';
import 'package:pcflash/usb_target_screen.dart';

class NoBluetooth extends BleOtaService {
  int scans = 0;
  @override
  Future<void> startScan() async {
    scans++;
    throw StateError('Bluetooth must stay off');
  }

  @override
  Future<void> disconnect() async {}
  @override
  Future<void> stopScan() async {}
  @override
  Stream<List<ScanResult>> get scanResults => const Stream.empty();
}

class UsbOwner extends ControlClient {
  int grants = 0;
  bool live = false;
  @override
  bool get authorized => live;
  @override
  bool get canReadStatus => live;
  @override
  bool get usesUsbDirect => true;
  @override
  Future<void> authorizeUsb(UsbAttachment usb,
      {bool Function()? isCurrent}) async {
    grants++;
    live = true;
  }

  @override
  Future<Map<String, dynamic>> pairingCode() async =>
      {'code': '0246', 'persistent': true};
  @override
  Future<void> refresh() async {}
  @override
  Future<void> shutdown() async {
    live = false;
  }
}

void main() {
  testWidgets('default USB startup grants control without a Bluetooth scan',
      (tester) async {
    tester.view.physicalSize = const Size(1000, 2600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    const usb = UsbAttachment('AABBCCDDEEFF', 'AABBCCDDEEFF:31', null, null);
    final board = NoBluetooth(), client = UsbOwner();
    final m = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    m.setMockMethodCallHandler(UsbLaunch.channel, (c) async {
      if (c.method == 'info') {
        return {'protocol': 1, 'device': 'test-board', 'usbSerial': usb.serial};
      }
      if (c.method == 'snapshot') {
        return {'serial': usb.serial, 'session': usb.session};
      }
      return null;
    });
    m.setMockMethodCallHandler(ScreenShare.channel, (c) async {
      if (c.method == 'captureSession') {
        return {
          'serial': usb.serial,
          'generation': 1,
          'needsAuthorization': false
        };
      }
      if (c.method == 'usbWindow') return '{"state":"idle"}';
      return jsonEncode({'active': true, 'capture': '共享中', 'task': ''});
    });
    addTearDown(() async {
      await TargetSession.release();
      m.setMockMethodCallHandler(UsbLaunch.channel, null);
      m.setMockMethodCallHandler(ScreenShare.channel, null);
    });
    await tester.pumpWidget(MaterialApp(
        home: UsbTargetScreen(
            attachment: usb,
            service: board,
            isCurrent: () => true,
            renewCapture: (_) async {},
            createControlClient: () => client)));
    await tester.pumpAndSettle();
    expect(client.grants, 1);
    expect(board.scans, 0);
    expect(find.text('0246'), findsOneWidget);
    expect(find.text('改用蓝牙中转（备用）'), findsOneWidget);
    expect(find.textContaining('USB 授权已建立'), findsWidgets);
    await tester.ensureVisible(find.text('改用蓝牙中转（备用）'));
    await tester.tap(find.text('改用蓝牙中转（备用）'));
    // Stream cancellation may complete outside the widget fake clock.
    await tester.runAsync(() async {
      await Future<void>.delayed(const Duration(milliseconds: 50));
    });
    await tester.pumpAndSettle();
    expect(board.scans, 1,
        reason: 'Bluetooth starts only after explicit choice');
    await tester.drag(find.byType(ListView), const Offset(0, 1800));
    await tester.pumpAndSettle();
    expect(find.byType(ProductError), findsWidgets);
    expect(client.grants, 1,
        reason: 'fallback failure never replays USB authorization');
    await tester.pumpWidget(const SizedBox());
  });
}
