import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/product_widgets.dart';
import 'package:pcflash/screen_share.dart';
import 'package:pcflash/usb_launch.dart';
import 'package:pcflash/usb_target_screen.dart';

void main() {
  for (final scenario in ['same-phase', 'other-phase', 'invalid-ready']) {
    testWidgets('target poll $scenario clears only proven recovered phase',
        (tester) async {
      tester.view.physicalSize = const Size(1000, 2400);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      const serial = 'AABBCCDDEE22';
      var mode = 'fail', captureFails = false;
      var now = DateTime(2030);
      final messenger =
          TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
      messenger.setMockMethodCallHandler(UsbLaunch.channel, (call) async {
        if (call.method == 'info') {
          return {'protocol': 1, 'device': 'test-board', 'usbSerial': serial};
        }
        return null;
      });
      messenger.setMockMethodCallHandler(ScreenShare.channel, (call) async {
        if (call.method == 'status') {
          return jsonEncode({'active': true, 'capture': '共享中', 'task': ''});
        }
        if (call.method == 'captureSession') {
          return {
            'serial': serial,
            'generation': 1,
            'needsAuthorization': false
          };
        }
        if (call.method == 'usbWindow') {
          if (mode == 'fail') {
            throw PlatformException(code: 'usb_window', message: 'temporary');
          }
          return jsonEncode({'state': mode});
        }
        return null;
      });
      addTearDown(() {
        messenger.setMockMethodCallHandler(UsbLaunch.channel, null);
        messenger.setMockMethodCallHandler(ScreenShare.channel, null);
      });
      await tester.pumpWidget(MaterialApp(
          home: UsbTargetScreen(
        attachment: UsbAttachment(serial, '$serial:$scenario', null, null),
        isCurrent: () => true,
        captureClock: () => now,
        renewCapture: (_) async {
          if (captureFails) throw StateError('capture-renew-failed');
        },
      )));
      await tester.pumpAndSettle();
      if (scenario == 'other-phase') {
        captureFails = true;
        now = now.add(const Duration(seconds: 61));
      }
      await tester.pump(const Duration(seconds: 2));
      await tester.pumpAndSettle();
      expect(find.byType(ProductError),
          scenario == 'other-phase' ? findsNWidgets(2) : findsOneWidget);
      if (scenario == 'invalid-ready') {
        mode = 'not_ready';
        await tester.pump(const Duration(seconds: 2));
        await tester.pumpAndSettle();
        expect(find.byType(ProductError), findsOneWidget,
            reason: 'HTTP200 invalid state is not success');
      }
      mode = 'ready';
      await tester.pump(const Duration(seconds: 2));
      await tester.pumpAndSettle();
      if (scenario == 'other-phase') {
        expect(find.byType(ProductError), findsOneWidget);
        expect(find.textContaining('capture-renew-failed'), findsOneWidget);
      } else {
        expect(find.byType(ProductError), findsNothing);
      }
      expect(find.text('结果已核验'), findsNothing);
      expect(find.textContaining('最近回执允许操作'), findsNothing);
      expect(find.textContaining('正在检查手机中转连接'), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
    });
  }
  testWidgets('late ready after STOP cannot clear stop failure or revive state',
      (tester) async {
    const serial = 'AABBCCDDEE33';
    final ready = Completer<String>();
    var windowCalls = 0, starts = 0;
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(UsbLaunch.channel, (call) async {
      if (call.method == 'info') {
        return {'protocol': 1, 'device': 'test-board', 'usbSerial': serial};
      }
      return null;
    });
    messenger.setMockMethodCallHandler(ScreenShare.channel, (call) async {
      if (call.method == 'status') {
        return '{"active":true,"capture":"共享中","task":""}';
      }
      if (call.method == 'captureSession') {
        return {'serial': serial, 'generation': 1, 'needsAuthorization': false};
      }
      if (call.method == 'usbWindow') {
        windowCalls++;
        if (windowCalls == 1) {
          throw PlatformException(code: 'usb_window');
        }
        return ready.future;
      }
      if (call.method == 'start') {
        starts++;
      }
      if (call.method == 'stop') {
        throw PlatformException(code: 'stop-failed');
      }
      return null;
    });
    addTearDown(() {
      messenger.setMockMethodCallHandler(UsbLaunch.channel, null);
      messenger.setMockMethodCallHandler(ScreenShare.channel, null);
    });
    await tester.pumpWidget(MaterialApp(
        home: UsbTargetScreen(
      attachment: const UsbAttachment(serial, 'stop-error-session', null, null),
      isCurrent: () => true,
      renewCapture: (_) async {},
    )));
    await tester.pumpAndSettle();
    await tester.pump(const Duration(seconds: 2));
    await tester.pumpAndSettle();
    await tester.pump(const Duration(seconds: 2));
    await tester.pump();
    expect(windowCalls, 2);
    await tester.scrollUntilVisible(find.text('停止控制与共享'), 150);
    await tester.tap(find.text('停止控制与共享'));
    await tester.pumpAndSettle();
    expect(find.textContaining('stop-failed'), findsOneWidget);
    ready.complete('{"state":"ready"}');
    await tester.pumpAndSettle();
    expect(find.textContaining('stop-failed'), findsOneWidget);
    expect(find.text('屏幕共享中'), findsNothing);
    expect(find.text('结果已核验'), findsNothing);
    expect(starts, 0);
    await tester.pumpWidget(const SizedBox());
  });
}
