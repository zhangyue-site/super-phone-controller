import 'dart:typed_data';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/button_detector.dart';

List<List<List<double>>> tensor() =>
    [List.generate(5, (_) => List.filled(2100, 0.0))];
void main() {
  test('private model descriptor pins shape format bounds and content identity',
      () {
    final m = {
      'available': true,
      'format': 'onnx',
      'version': 'button-v3',
      'sha256': 'a' * 64,
      'size': 12000000,
      'inputWidth': 320,
      'inputHeight': 320,
      'outputLayout': 'xywh-score',
      'preprocess': 'stretch-rgb-0-1'
    };
    expect(ButtonModelManifest.parse(m).sha256, 'a' * 64);
    for (final bad in [
      {...m, 'size': 33554433},
      {...m, 'sha256': '../key'},
      {...m, 'inputWidth': 640},
      {...m, 'format': 'url'},
      {...m, 'preprocess': 'unknown'}
    ]) {
      expect(() => ButtonModelManifest.parse(bad), throwsFormatException);
    }
  });
  test(
      'detector maps xywh to normalized boxes and suppresses duplicate targets',
      () {
    final t = tensor();
    t[0][0][0] = 160;
    t[0][1][0] = 160;
    t[0][2][0] = 80;
    t[0][3][0] = 40;
    t[0][4][0] = .9;
    for (var i = 0; i < 5; i++) {
      t[0][i][1] = t[0][i][0];
    }
    t[0][4][1] = .8;
    final boxes = decodeButtonOutput(t);
    expect(boxes.length, 1);
    expect(boxes.single.x, .375);
    expect(boxes.single.y, .4375);
    expect(boxes.single.width, .25);
    expect(boxes.single.height, .125);
  });
  test('shape corruption non-finite values and invalid scores fail closed', () {
    expect(() => decodeButtonOutput([[]]), throwsFormatException);
    final t = tensor();
    t[0][4][0] = double.nan;
    expect(() => decodeButtonOutput(t), throwsFormatException);
    t[0][4][0] = 1.1;
    expect(() => decodeButtonOutput(t), throwsFormatException);
  });
  test('boxes are clipped to visible frame and zero area is discarded', () {
    final t = tensor();
    t[0][0][0] = 0;
    t[0][1][0] = 10;
    t[0][2][0] = 40;
    t[0][3][0] = 40;
    t[0][4][0] = .9;
    final b = decodeButtonOutput(t).single;
    expect(b.x, 0);
    expect(b.y, 0);
    expect(b.width, .0625);
    expect(b.height, .09375);
  });
  test(
      'NCHW preprocessing validates JPEG rather than treating arbitrary bytes as a frame',
      () {
    expect(() => preprocessButtonJpeg(Uint8List.fromList([1, 2, 3])),
        throwsFormatException);
  });
}
