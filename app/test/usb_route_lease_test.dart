import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/usb_launch.dart';
import 'package:pcflash/usb_route_lease.dart';

void main() {
  const old = UsbAttachment('AABBCCDDEEFF', 'AABBCCDDEEFF:1', null, null);
  const reattached =
      UsbAttachment('AABBCCDDEEFF', 'AABBCCDDEEFF:2', null, null);
  const other = UsbAttachment('112233445566', '112233445566:1', null, null);
  testWidgets(
      'HID reenumeration retains selected board; real detach ends route',
      (tester) async {
    var lost = 0;
    final lease = UsbRouteLease(() => lost++);
    lease.select(old);
    lease.update(null);
    await tester.pump(const Duration(seconds: 4));
    lease.update(reattached);
    await tester.pump(const Duration(seconds: 4));
    expect(lost, 0);
    lease.update(null);
    await tester.pump(const Duration(seconds: 8));
    expect(lost, 1);
    lease.update(reattached);
    expect(lost, 1); // no automatic ownership resurrection
    lease.dispose();
  });
  testWidgets(
      'different USB board immediately ends route; dispose cancels timer',
      (tester) async {
    var lost = 0;
    final lease = UsbRouteLease(() => lost++);
    lease.select(old);
    lease.update(other);
    expect(lost, 1);
    lease.select(old);
    lease.update(null);
    lease.dispose();
    await tester.pump(const Duration(seconds: 4));
    expect(lost, 1);
  });
}
