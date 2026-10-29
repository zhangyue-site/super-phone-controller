import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
// ignore: depend_on_referenced_packages
import 'package:flutter_blue_plus_platform_interface/flutter_blue_plus_platform_interface.dart';
import 'package:pcflash/device_screen.dart';
import 'package:pcflash/usb_target_screen.dart';
import 'package:pcflash/usb_launch.dart';
import 'package:pcflash/screen_share.dart';

final class NoBluetoothPlatform extends FlutterBluePlusPlatform {
  int reads = 0;
  @override
  Future<BmBluetoothAdapterState> getAdapterState(
      BmBluetoothAdapterStateRequest request) async {
    reads++;
    return BmBluetoothAdapterState(adapterState: BmAdapterStateEnum.off);
  }
}

void main() {
  testWidgets(
      'target USB identity failure stays read-only without legacy command fallback',
      (tester) async {
    FlutterBluePlusPlatform.instance = NoBluetoothPlatform();
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(UsbLaunch.channel, (call) async {
      if (call.method == 'snapshot') {
        return {'serial': 'AABBCCDDEEFF', 'session': 'AABBCCDDEEFF:1'};
      }
      if (call.method == 'info') {
        throw PlatformException(code: 'usb_proof_failed');
      }
      return null;
    });
    messenger.setMockMethodCallHandler(ScreenShare.channel,
        (call) async => '{"active":false,"capture":"未共享","task":""}');
    await tester
        .pumpWidget(const MaterialApp(home: DeviceScreen(targetOnly: true)));
    await tester.pumpAndSettle();
    expect(find.text('被控手机'), findsOneWidget);
    expect(find.textContaining('连接未完成'), findsOneWidget);
    expect(find.text('通过蓝牙连接旧版控制板'), findsNothing);
    expect(find.byType(TextField), findsNothing);
    expect(find.text('停止控制与共享'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
    messenger.setMockMethodCallHandler(UsbLaunch.channel, null);
    messenger.setMockMethodCallHandler(ScreenShare.channel, null);
  });

  for (final fail in [false, true]) {
    testWidgets('late startup snapshot ($fail) cannot replace newer USB attach',
        (tester) async {
      final bluetooth = NoBluetoothPlatform();
      FlutterBluePlusPlatform.instance = bluetooth;
      final initial = Completer<Map<String, dynamic>>();
      final messenger =
          TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
      var infoCalls = 0;
      var captureCalls = 0;
      messenger.setMockMethodCallHandler(UsbLaunch.channel, (call) async {
        if (call.method == 'snapshot') return initial.future;
        if (call.method == 'info') {
          infoCalls++;
          throw PlatformException(code: 'test-no-board');
        }
        return null;
      });
      messenger.setMockMethodCallHandler(ScreenShare.channel, (call) async {
        if (call.method == 'start' || call.method == 'startUsb') {
          captureCalls++;
        }
        return '{"active":false,"capture":"未共享","task":""}';
      });
      addTearDown(
          () => messenger.setMockMethodCallHandler(ScreenShare.channel, null));
      addTearDown(
          () => messenger.setMockMethodCallHandler(UsbLaunch.channel, null));
      await tester.pumpWidget(const MaterialApp(home: DeviceScreen()));
      await tester.pump();
      const codec = StandardMethodCodec();
      // ignore: deprecated_member_use
      await messenger.handlePlatformMessage(
          UsbLaunch.channel.name,
          codec.encodeMethodCall(const MethodCall('changed', {
            'serial': 'AABBCCDDEEFF',
            'session': 'AABBCCDDEEFF:2',
            'remoteId': 'AA:BB:CC:DD:EE:01',
            'deviceId': 'epaper-01',
          })),
          (_) {});
      await tester.pumpAndSettle();
      expect(
          tester
              .widget<UsbTargetScreen>(find.byType(UsbTargetScreen))
              .attachment
              .serial,
          'AABBCCDDEEFF');
      expect(find.text('已识别控制板'), findsOneWidget);
      expect(bluetooth.reads, 0);
      expect(infoCalls, 1);
      await tester.pump(const Duration(seconds: 6));
      expect(infoCalls, 1);
      if (fail) {
        initial.completeError(PlatformException(code: 'stale'));
      } else {
        initial
            .complete({'serial': 'AABBCCDDEEFF', 'session': 'AABBCCDDEEFF:1'});
      }
      await tester.pumpAndSettle();
      expect(
          tester
              .widget<UsbTargetScreen>(find.byType(UsbTargetScreen))
              .attachment
              .serial,
          'AABBCCDDEEFF');
      expect(find.text('已识别控制板'), findsOneWidget);
      expect(find.textContaining('首次连接：'), findsNothing);
      expect(find.text('请打开手机蓝牙，开启后会自动寻找控制板'), findsNothing);
      expect(find.text('被控手机'), findsOneWidget);
      expect(bluetooth.reads, 0);
      expect(infoCalls, 1);
      expect(captureCalls, 0);
      expect(find.textContaining('连接未完成'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox());
      await tester.pump();
    });
  }
}
