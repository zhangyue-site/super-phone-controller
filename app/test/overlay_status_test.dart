import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/overlay_status.dart';

void main() {
  test('missing client is unknown connection, not denied permission', () {
    expect(
        gatewayIndicator(hasClient: false, sessionReady: false), (3, '本机未中转'));
  });
  test('connection recovery does not claim a board authorization rejection',
      () {
    expect(
        gatewayIndicator(hasClient: true, sessionReady: false), (1, '本机中转待恢复'));
  });
  test('healthy session does not claim HID permission', () {
    expect(
        gatewayIndicator(hasClient: true, sessionReady: true), (0, '本机中转已连接'));
  });
}
