import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/usb_launch.dart';

void main() {
  Map<String, dynamic> attachment({bool bound = true}) => {
        'serial': 'AABBCCDDEEFF',
        'session': 'AABBCCDDEEFF:1',
        if (bound) 'remoteId': 'AA:BB:CC:DD:EE:01',
        if (bound) 'deviceId': 'epaper-01',
      };
  test('native UUID attachment sessions remain unique and validate identity', () {
    const first = 'AABBCCDDEEFF:0:12345678-1234-1234-1234-123456789abc';
    const second = 'AABBCCDDEEFF:0:12345678-1234-1234-1234-123456789abd';
    final a = UsbAttachment.parse({...attachment(), 'session': first});
    final b = UsbAttachment.parse({...attachment(), 'session': second});
    final gate = UsbAutoShareGate();
    expect(gate.claim(a, bluetoothOn: true, opening: false), isTrue);
    expect(gate.claim(a, bluetoothOn: true, opening: false), isFalse);
    expect(gate.claim(b, bluetoothOn: true, opening: false), isTrue);
    for (final invalid in [
      'OTHER:0:12345678-1234-1234-1234-123456789abc',
      'AABBCCDDEEFF:0:garbage',
      'AABBCCDDEEFF:-1:12345678-1234-1234-1234-123456789abc',
      'AABBCCDDEEFF:0:12345678-1234-1234-1234-123456789abc:extra'
    ]) {
      expect(() => UsbAttachment.parse({...attachment(), 'session': invalid}),
          throwsFormatException);
    }
  });
  test('USB binding requires complete validated identity', () {
    expect(UsbAttachment.parse(attachment()).isBound, isTrue);
    expect(UsbAttachment.parse(attachment(bound: false)).isBound, isFalse);
    expect(() => UsbAttachment.parse({...attachment(), 'serial': ''}),
        throwsFormatException);
    expect(() => UsbAttachment.parse({...attachment(), 'remoteId': 'nearby'}),
        throwsFormatException);
    expect(() => UsbAttachment.parse({...attachment(), 'deviceId': null}),
        throwsFormatException);
    expect(() => UsbAttachment.parse({...attachment(), 'session': 'OTHER:1'}),
        throwsFormatException);
  });
  test(
      'one automatic attempt per attachment; Bluetooth off does not consume it',
      () {
    final gate = UsbAutoShareGate();
    final usb = UsbAttachment.parse(attachment());
    expect(gate.claim(usb, bluetoothOn: false, opening: false), isFalse);
    expect(gate.claim(usb, bluetoothOn: true, opening: true), isFalse);
    expect(gate.claim(usb, bluetoothOn: true, opening: false), isTrue);
    expect(gate.claim(usb, bluetoothOn: true, opening: false), isFalse);
    expect(
        gate.claim(
            UsbAttachment.parse({...attachment(), 'session': 'AABBCCDDEEFF:2'}),
            bluetoothOn: true,
            opening: false),
        isTrue);
  });
  test('first pairing never chooses a nearby BLE board automatically', () {
    expect(
        UsbAutoShareGate().claim(UsbAttachment.parse(attachment(bound: false)),
            bluetoothOn: true, opening: false),
        isFalse);
  });
  test('remembered board must match both BLE address and server identity', () {
    final usb = UsbAttachment.parse(attachment());
    usb.validateBoard('aa:bb:cc:dd:ee:01', 'epaper-01');
    expect(() => usb.validateBoard('AA:BB:CC:DD:EE:02', 'epaper-01'),
        throwsStateError);
    expect(() => usb.validateBoard('AA:BB:CC:DD:EE:01', 'other-board'),
        throwsStateError);
  });
}
