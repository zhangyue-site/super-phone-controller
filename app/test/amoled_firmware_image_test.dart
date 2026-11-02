import 'dart:typed_data';
import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/firmware_image.dart';
import 'firmware_image_test.dart' show fixture;

Uint8List amoledImage() {
  final b = fixture();
  b.fillRange(48, 112, 0);
  b.setAll(48, '0.3.0-amoled'.codeUnits);
  b.setAll(80, 'phone_controller_amoled'.codeUnits);
  var sum = 0xef;
  for (var i = 32; i < 4080; i++) {
    sum ^= b[i];
  }
  b[4095] = sum;
  b.setAll(4096, sha256.convert(b.sublist(0, 4096)).bytes);
  return b;
}

void main() {
  test('AMOLED image accepted only for its explicit connected board target',
      () {
    final target = FirmwareImage.parse(amoledImage(),
        boardModel: 'esp32-s3-touch-amoled-2.16');
    expect(target.version, '0.3.0-amoled');
    expect(() => FirmwareImage.parse(amoledImage()), throwsFormatException);
    expect(
        () => FirmwareImage.parse(fixture(),
            boardModel: 'esp32-s3-touch-amoled-2.16'),
        throwsFormatException);
  });
  test('AMOLED uses monotonic target-specific semantic versions', () {
    final image = FirmwareImage.parse(amoledImage(),
        boardModel: 'esp32-s3-touch-amoled-2.16');
    expect(() => image.assertUpgradeAllowed('0.2.1-amoled'), returnsNormally);
    for (final v in [
      '0.3.0-amoled',
      '0.4.0-amoled',
      '2026.10.26-server1',
      'legacy'
    ]) {
      expect(() => image.assertUpgradeAllowed(v), throwsStateError);
    }
  });
}
