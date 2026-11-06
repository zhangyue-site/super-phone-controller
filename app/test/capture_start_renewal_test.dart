import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/screen_share.dart';
import 'package:pcflash/usb_launch.dart';
import 'package:pcflash/usb_target_screen.dart';
import 'package:pcflash/target_session.dart';

void main() {
  for (final fails in [false, true]) {
    testWidgets('existing near-expiry capture renews on entry; failure=$fails',
        (tester) async {
      final messenger =
          TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
      final usb = UsbAttachment('RENEWTEST', 'near-expiry-$fails', null, null);
      var now = DateTime(2026);
      var renews = 0, starts = 0, stops = 0;
      TargetSession.noteCapture(
          usb, now.subtract(const Duration(seconds: 265)));
      messenger.setMockMethodCallHandler(
          UsbLaunch.channel,
          (call) async =>
              {'protocol': 1, 'device': 'board', 'usbSerial': usb.serial});
      messenger.setMockMethodCallHandler(ScreenShare.channel, (call) async {
        if (call.method == 'status') {
          return '{"active":true,"capture":"sharing"}';
        }
        if (call.method == 'captureSession') {
          return {
            'generation': 1,
            'serial': usb.serial,
            'needsAuthorization': false
          };
        }
        if (call.method == 'usbWindow') {
          throw PlatformException(code: 'offline');
        }
        if (call.method == 'start') starts++;
        if (call.method == 'stop') stops++;
        return null;
      });
      addTearDown(() {
        messenger.setMockMethodCallHandler(UsbLaunch.channel, null);
        messenger.setMockMethodCallHandler(ScreenShare.channel, null);
      });
      Future<void> renew(UsbAttachment _) async {
        renews++;
        if (fails) throw StateError('offline');
      }

      await tester.pumpWidget(MaterialApp(
          home: UsbTargetScreen(
              attachment: usb,
              isCurrent: () => true,
              captureClock: () => now,
              renewCapture: renew)));
      await tester.pumpAndSettle();
      expect(renews, 1,
          reason: 'page entry must not postpone a nearly expired credential');
      await TargetSession.maintainCapture(usb,
          clock: () => now,
          renew: (_) async {
            renews++;
          });
      expect(renews, fails ? 2 : 1,
          reason: 'failed renewal must not advance the clock');
      now = now.add(const Duration(seconds: 61));
      await TargetSession.maintainCapture(usb,
          clock: () => now,
          renew: (_) async {
            renews++;
          });
      expect(renews, fails ? 3 : 2);
      expect(starts, 0);
      expect(stops, 0);
      await tester.pumpWidget(const SizedBox());
      await tester.pump();
    });
  }
}
