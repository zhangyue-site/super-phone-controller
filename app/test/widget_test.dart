import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
// ignore: depend_on_referenced_packages
import 'package:flutter_blue_plus_platform_interface/flutter_blue_plus_platform_interface.dart';
import 'package:pcflash/main.dart';
import 'package:pcflash/device_screen.dart';
import 'package:pcflash/usb_launch.dart';
import 'package:pcflash/screen_share.dart';

final class BluetoothOffPlatform extends FlutterBluePlusPlatform {
  int adapterReads = 0;
  @override
  Future<BmBluetoothAdapterState> getAdapterState(
      BmBluetoothAdapterStateRequest request) async {
    adapterReads++;
    return BmBluetoothAdapterState(adapterState: BmAdapterStateEnum.off);
  }
}

void main() {
  testWidgets(
      'role entry controller opens pairing without Bluetooth or capture',
      (tester) async {
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(UsbLaunch.channel, (_) async => null);
    addTearDown(
        () => messenger.setMockMethodCallHandler(UsbLaunch.channel, null));
    final bluetooth = BluetoothOffPlatform();
    FlutterBluePlusPlatform.instance = bluetooth;
    await tester.pumpWidget(const PcFlashApp());
    await tester.pumpAndSettle();
    expect(find.text('选择这台手机的用途'), findsOneWidget);
    expect(find.text('请打开手机蓝牙，开启后会自动寻找控制板'), findsNothing);
    expect(tester.widget<MaterialApp>(find.byType(MaterialApp)).themeMode,
        ThemeMode.system);
    await tester.tap(find.text('控制手机'));
    await tester.pumpAndSettle();
    expect(find.text('输入被控手机的连接码'), findsOneWidget);
    expect(bluetooth.adapterReads, 0);
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets('role home BLE maintenance needs no USB proof or screen consent',
      (tester) async {
    final calls = <String>[];
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(UsbLaunch.channel, (call) async {
      calls.add('usb:${call.method}');
      return null;
    });
    messenger.setMockMethodCallHandler(ScreenShare.channel, (call) async {
      calls.add('screen:${call.method}');
      return null;
    });
    addTearDown(() {
      messenger.setMockMethodCallHandler(UsbLaunch.channel, null);
      messenger.setMockMethodCallHandler(ScreenShare.channel, null);
    });
    FlutterBluePlusPlatform.instance = BluetoothOffPlatform();
    await tester.pumpWidget(const PcFlashApp());
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('蓝牙固件维护'));
    await tester.tap(find.text('蓝牙固件维护'));
    await tester.pumpAndSettle();
    expect(find.text('控制板升级'), findsOneWidget);
    expect(find.text('等待连接USB控制板'), findsNothing);
    expect(calls.every((call) => call == 'usb:snapshot'), isTrue);
    expect(calls.where((call) => call.startsWith('screen:')), isEmpty);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets('target role without USB waits without Bluetooth scan',
      (tester) async {
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(UsbLaunch.channel, (_) async => null);
    addTearDown(
        () => messenger.setMockMethodCallHandler(UsbLaunch.channel, null));
    final bluetooth = BluetoothOffPlatform();
    FlutterBluePlusPlatform.instance = bluetooth;
    await tester.pumpWidget(const PcFlashApp());
    await tester.pumpAndSettle();
    await tester.tap(find.text('被控手机'));
    await tester.pumpAndSettle();
    expect(find.text('等待连接USB控制板'), findsOneWidget);
    expect(bluetooth.adapterReads, 0);
    expect(find.text('重新寻找控制板'), findsNothing);
    await tester.pageBack();
    await tester.pumpAndSettle();
    expect(find.text('选择这台手机的用途'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets(
      'recognized startup USB automatically routes to target without starting a controller',
      (tester) async {
    final identity = Completer<Map<String, dynamic>>();
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(UsbLaunch.channel, (call) async {
      if (call.method == 'snapshot') {
        return {'serial': 'AABBCCDDEEFF', 'session': 'AABBCCDDEEFF:1'};
      }
      if (call.method == 'info') {
        return identity.future;
      }
      return null;
    });
    addTearDown(
        () => messenger.setMockMethodCallHandler(UsbLaunch.channel, null));
    final bluetooth = BluetoothOffPlatform();
    FlutterBluePlusPlatform.instance = bluetooth;
    await tester.pumpWidget(const PcFlashApp());
    await tester.pumpAndSettle();
    expect(find.text('USB 控制板'), findsOneWidget);
    expect(find.text('正在连接'), findsOneWidget);
    expect(find.byType(TextFormField), findsNothing);
    expect(bluetooth.adapterReads, 0);
    await tester.pumpWidget(const SizedBox());
    identity.complete(
        {'protocol': 1, 'device': 'test-board', 'usbSerial': 'AABBCCDDEEFF'});
    await tester.pump();
    expect(tester.takeException(), isNull);
  });
  testWidgets('theme picker applies light and dark modes', (tester) async {
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(UsbLaunch.channel, (_) async => null);
    addTearDown(
        () => messenger.setMockMethodCallHandler(UsbLaunch.channel, null));
    await tester.pumpWidget(const PcFlashApp());
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('显示主题'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('深色'));
    await tester.pumpAndSettle();
    expect(tester.widget<MaterialApp>(find.byType(MaterialApp)).themeMode,
        ThemeMode.dark);
    await tester.tap(find.byTooltip('显示主题'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('浅色'));
    await tester.pumpAndSettle();
    expect(tester.widget<MaterialApp>(find.byType(MaterialApp)).themeMode,
        ThemeMode.light);
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets('Bluetooth off shows actionable recovery without scanning',
      (tester) async {
    tester.view.physicalSize = const Size(320, 568);
    tester.view.devicePixelRatio = 1;
    tester.platformDispatcher.textScaleFactorTestValue = 1.6;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(UsbLaunch.channel, (_) async => null);
    addTearDown(
        () => messenger.setMockMethodCallHandler(UsbLaunch.channel, null));
    FlutterBluePlusPlatform.instance = BluetoothOffPlatform();
    await tester.pumpWidget(const MaterialApp(home: DeviceScreen()));
    await tester.pumpAndSettle();
    expect(find.text('控制板升级'), findsOneWidget);
    expect(find.text('请打开手机蓝牙，开启后会自动寻找控制板'), findsOneWidget);
    expect(find.text('重新寻找控制板'), findsOneWidget);
    expect(find.text('正在寻找板子…'), findsNothing);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
    await tester.pump();
  });
}
