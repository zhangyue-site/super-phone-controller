import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/screen_share.dart';
import 'package:pcflash/usb_launch.dart';
import 'package:pcflash/usb_target_screen.dart';

void main() {
  testWidgets('window failure cannot block capture renewal or end projection',
      (tester) async {
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    var now = DateTime(2026);
    var renews = 0, windows = 0, starts = 0, stops = 0;
    messenger.setMockMethodCallHandler(
        UsbLaunch.channel,
        (call) async => call.method == 'sign'
            ? {
                'device': 'board',
                'usbSerial': 'FFEEDDCCBBAA',
                'proof': 'b' * 64
              }
            : {'protocol': 1, 'device': 'board', 'usbSerial': 'FFEEDDCCBBAA'});
    addTearDown(() {
      messenger.setMockMethodCallHandler(ScreenShare.channel, null);
      messenger.setMockMethodCallHandler(UsbLaunch.channel, null);
    });
    var contexts = 0;
    messenger.setMockMethodCallHandler(ScreenShare.channel, (call) async {
      if (call.method == 'status') {
        return '{"active":true,"capture":"共享中","task":""}';
      }
      if (call.method == 'captureSession') {
        contexts++;
        return {
          'generation': 1,
          'serial': 'FFEEDDCCBBAA',
          'needsAuthorization': false
        };
      }
      if (call.method == 'usbWindow') {
        windows++;
        throw PlatformException(code: 'network_down');
      }
      if (call.method == 'start') starts++;
      if (call.method == 'stop') stops++;
      return null;
    });
    await tester.pumpWidget(MaterialApp(
        home: UsbTargetScreen(
            attachment:
                const UsbAttachment('FFEEDDCCBBAA', 's-isolation', null, null),
            isCurrent: () => true,
            captureClock: () => now,
            renewCapture: (_) async {
              renews++;
            })));
    await tester.pumpAndSettle();
    await tester.pump(const Duration(seconds: 2));
    await tester.pumpAndSettle();
    now = now.add(const Duration(seconds: 61));
    await tester.pump(const Duration(seconds: 2));
    await tester.pumpAndSettle();
    expect(contexts, 3);
    expect(windows, 2);
    expect(starts, 0);
    expect(stops, 0);
    expect(renews, 2); // The failing window did not block due renewal.
    await tester.pumpWidget(const SizedBox());
    await tester.pump();
  });
}
