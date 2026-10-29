import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/control_client.dart';
import 'package:pcflash/ble_ota_service.dart';
import 'package:pcflash/control_screen.dart';
import 'package:pcflash/role_home.dart';
import 'package:pcflash/screen_share.dart';
import 'package:pcflash/target_session.dart';
import 'package:pcflash/product_widgets.dart';
import 'package:pcflash/product_settings.dart';
import 'package:pcflash/theme.dart';
import 'package:pcflash/usb_launch.dart';
import 'package:pcflash/usb_target_screen.dart';

class RenderClient extends ControlClient {
  RenderClient({this.fail = false});
  final bool fail;
  int commands = 0;
  @override
  bool get authorized => true;
  @override
  bool get canReadStatus => true;
  @override
  bool get isPaired => true;
  @override
  Future<Map<String, dynamic>> command(String operation,
      {String? text,
      String? taskId,
      String? skillId,
      Map<String, String>? parameters}) async {
    commands++;
    if (fail) {
      throw StateError(
          List.filled(12, '连接暂不可用，请保留当前任务，检查被控手机画面后再重新规划。').join());
    }
    return {
      'state': 'pending',
      'task_id': 'a' * 32,
      'reply': '计划：打开设置。确认后会检查被控手机画面与操作许可，再由控制板执行。',
      'terminal': false
    };
  }
}

class RetainedClient extends RenderClient {
  int shutdowns = 0;
  @override
  Future<void> shutdown() async {
    shutdowns++;
  }
}

class RetainedBoard extends BleOtaService {
  int disconnects = 0;
  @override
  Future<void> disconnect() async {
    disconnects++;
  }
}

class LostUpgradeClient extends RenderClient {
  @override
  bool get canWifiUpgrade => true;
  @override
  void requestWifiUpgrade() {
    throw StateError('连接已改变，请重新连接控制板');
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final output = Platform.environment['PRODUCT_SCREENSHOTS_DIR'];
  setUpAll(() async {
    if (output == null) return;
    for (final entry in [
      (
        'ProductEvidence',
        '/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc'
      ),
      (
        'MaterialIcons',
        '/tmp/phone-controller-render-test'
      )
    ]) {
      final bytes = File(entry.$2).readAsBytesSync();
      await (FontLoader(entry.$1)
            ..addFont(Future<ByteData>.value(ByteData.sublistView(bytes))))
          .load();
    }
  });
  for (final dark in [false, true]) {
    for (final page in ['roles', 'task', 'target']) {
      testWidgets('product $page ${dark ? 'dark' : 'light'} render',
          (tester) async {
        tester.view.physicalSize = const Size(390, 844);
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);
        final messenger =
            TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
        var starts = 0, stops = 0;
        messenger.setMockMethodCallHandler(ScreenShare.channel, (call) async {
          if (call.method == 'status') {
            return jsonEncode({
              'active': true,
              'capture': '共享授权有效，等待新的真实画面',
              'task': jsonEncode({
                'state': 'idle',
                'reply': '尚未收到任务结果',
                'pointerReady': false,
                'skills': [],
                'barrier': 'ab' * 16
              })
            });
          }
          if (call.method == 'captureSession') {
            return {
              'generation': 42,
              'serial': '00112233FF00',
              'needsAuthorization': false
            };
          }
          if (call.method == 'usbWindow') return '{"state":"idle"}';
          if (call.method == 'start') starts++;
          if (call.method == 'stop') stops++;
          return null;
        });
        messenger.setMockMethodCallHandler(
            UsbLaunch.channel,
            (call) async => call.method == 'snapshot'
                ? {'serial': '00112233FF00', 'session': '00112233FF00:7'}
                : {
                    'protocol': 1,
                    'device': 'demo-board',
                    'usbSerial': '00112233FF00'
                  });
        addTearDown(() {
          messenger.setMockMethodCallHandler(ScreenShare.channel, null);
          messenger.setMockMethodCallHandler(UsbLaunch.channel, null);
        });
        var theme = dark ? AppTheme.build() : AppTheme.light();
        if (output != null) {
          theme = theme.copyWith(
              textTheme: theme.textTheme.apply(fontFamily: 'ProductEvidence'),
              primaryTextTheme:
                  theme.primaryTextTheme.apply(fontFamily: 'ProductEvidence'));
        }
        final child = switch (page) {
          'roles' => RoleHome(
              onController: () {}, onTarget: () {}, onMaintenance: () {}),
          'task' => ControlScreen(client: RenderClient()),
          _ => UsbTargetScreen(
              attachment: const UsbAttachment(
                  '00112233FF00', '00112233FF00:7', null, null),
              isCurrent: () => true)
        };
        await tester.pumpWidget(MaterialApp(
            theme: theme,
            home: RepaintBoundary(
                key: const Key('product-render'), child: child)));
        await tester.pumpAndSettle();
        if (page == 'task') {
          await tester.enterText(find.byType(TextField), '打开设置');
          await tester.tap(find.text('生成计划'));
          await tester.pumpAndSettle();
          tester.testTextInput.hide();
          await tester.pump();
        }
        if (page == 'target') {
          await tester.pump(const Duration(seconds: 2));
          await tester.pumpAndSettle();
        }
        expect(tester.takeException(), isNull);
        if (output != null) {
          await tester.runAsync(() async {
            final boundary = tester.renderObject<RenderRepaintBoundary>(
                find.byKey(const Key('product-render')));
            final image = await boundary.toImage(pixelRatio: 1);
            final bytes =
                await image.toByteData(format: ui.ImageByteFormat.png);
            final dir = Directory(output)..createSync(recursive: true);
            File('${dir.path}/$page-${dark ? 'dark' : 'light'}.png')
                .writeAsBytesSync(bytes!.buffer.asUint8List());
            image.dispose();
          });
        }
        expect(starts, 0);
        expect(stops, 0);
        await tester.pumpWidget(const SizedBox());
        await tester.pump();
        expect(stops, 0); // Merely leaving the page never stops native capture.
      });
    }
  }
  testWidgets(
      '200 percent long task error keeps STOP reachable without overflow',
      (tester) async {
    tester.view.physicalSize = const Size(320, 568);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(MaterialApp(
        theme: AppTheme.light(),
        builder: (context, child) => MediaQuery(
            data: MediaQuery.of(context)
                .copyWith(textScaler: const TextScaler.linear(2)),
            child: child!),
        home: ControlScreen(client: RenderClient(fail: true))));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.byType(TextField), 160,
        scrollable: find.byType(Scrollable).first);
    await tester.enterText(find.byType(TextField), '检查输入框');
    await tester.ensureVisible(find.text('生成计划'));
    await tester.tap(find.text('生成计划'));
    await tester.pumpAndSettle();
    expect(find.text('停止手机操作'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets('200 percent target errors and settings remain scrollable',
      (tester) async {
    tester.view.physicalSize = const Size(320, 568);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    for (final page in [
      Scaffold(
          appBar: AppBar(title: const Text('被控状态')),
          body: ListView(children: [
            TargetStatusOverview(
                board: '已识别控制板',
                capture: '共享授权有效，等待真实画面',
                permission: '执行时检查操作许可',
                network: '当前联网方式尚待检查',
                error: List.filled(12, '连接暂不可用，原共享会保留，请检查连接后重试。').join())
          ])),
      const ProductSettingsScreen()
    ]) {
      await tester.pumpWidget(MaterialApp(
          theme: AppTheme.light(),
          builder: (context, child) => MediaQuery(
              data: MediaQuery.of(context)
                  .copyWith(textScaler: const TextScaler.linear(2)),
              child: child!),
          home: page));
      await tester.pumpAndSettle();
      await tester.drag(find.byType(ListView).first, const Offset(0, -500));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox());
    }
  });
  testWidgets(
      'established phone relay is owned by the app across target navigation',
      (tester) async {
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    final client = RetainedClient();
    final service = RetainedBoard();
    const usb = UsbAttachment('99887766FF00', '99887766FF00:1', null, null);
    messenger.setMockMethodCallHandler(
        UsbLaunch.channel,
        (_) async =>
            {'protocol': 1, 'device': 'demo', 'usbSerial': usb.serial});
    messenger.setMockMethodCallHandler(ScreenShare.channel,
        (_) async => '{"active":true,"capture":"共享中","task":""}');
    addTearDown(() {
      messenger.setMockMethodCallHandler(UsbLaunch.channel, null);
      messenger.setMockMethodCallHandler(ScreenShare.channel, null);
    });
    TargetSession.retain(usb, client, service);
    await tester.pumpWidget(MaterialApp(
        home: UsbTargetScreen(
            attachment: usb, service: service, isCurrent: () => true)));
    await tester.pumpAndSettle();
    await tester.pumpWidget(const SizedBox());
    await tester.pump();
    expect(client.shutdowns, 0);
    expect(service.disconnects, 0);
    await TargetSession.release();
    expect(client.shutdowns, 1);
    expect(service.disconnects, 1);
  });
  testWidgets(
      'safe example chips only fill a draft without submitting or confirming',
      (tester) async {
    final client = RenderClient();
    await tester.pumpWidget(MaterialApp(
        theme: AppTheme.light(), home: ControlScreen(client: client)));
    await tester.pumpAndSettle();
    for (final example in ['打开设置', '打开设置搜索电池']) {
      await tester.scrollUntilVisible(
          find.widgetWithText(ActionChip, example), 120,
          scrollable: find.byType(Scrollable).first);
      await tester.tap(find.widgetWithText(ActionChip, example));
      await tester.pump();
      expect(tester.widget<TextField>(find.byType(TextField)).controller!.text,
          example);
      expect(client.commands, 0);
      expect(find.text('确认执行'), findsNothing);
    }
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets('upgrade connection loss remains an explicit unconfirmed error',
      (tester) async {
    await tester.pumpWidget(MaterialApp(
        theme: AppTheme.light(),
        home: ProductSettingsScreen(client: LostUpgradeClient())));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('控制板 Wi-Fi 升级'), 120,
        scrollable: find.byType(Scrollable).first);
    await tester.tap(find.text('控制板 Wi-Fi 升级'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('检查并请求升级'));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.textContaining('升级请求未确认'), 120,
        scrollable: find.byType(Scrollable).first);
    expect(find.textContaining('升级请求未确认'), findsOneWidget);
    expect(find.textContaining('已请求控制板检查更新'), findsNothing);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets(
      'app owner continues capture checks after target view is disposed',
      (tester) async {
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    var contexts = 0, stops = 0;
    messenger.setMockMethodCallHandler(
        UsbLaunch.channel,
        (call) async => call.method == 'snapshot'
            ? {'serial': '11223344FF00', 'session': '11223344FF00:1'}
            : {'protocol': 1, 'device': 'demo', 'usbSerial': '11223344FF00'});
    messenger.setMockMethodCallHandler(ScreenShare.channel, (call) async {
      if (call.method == 'status') {
        return '{"active":true,"capture":"共享中","task":""}';
      }
      if (call.method == 'captureSession') {
        contexts++;
        return {
          'generation': 1,
          'serial': '11223344FF00',
          'needsAuthorization': false
        };
      }
      if (call.method == 'usbWindow') return '{"state":"idle"}';
      if (call.method == 'stop') stops++;
      return null;
    });
    addTearDown(() {
      messenger.setMockMethodCallHandler(ScreenShare.channel, null);
      messenger.setMockMethodCallHandler(UsbLaunch.channel, null);
    });
    await tester.pumpWidget(MaterialApp(
        home: UsbTargetScreen(
            attachment: const UsbAttachment(
                '11223344FF00', '11223344FF00:1', null, null),
            isCurrent: () => true)));
    await tester.pumpAndSettle();
    await tester.pumpWidget(const SizedBox());
    await tester.pump();
    await TargetSession.maintain();
    expect(contexts, 1);
    expect(stops, 0);
  });
}
