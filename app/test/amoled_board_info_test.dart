import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/board_info.dart';

void main() {
  Map<String, dynamic> info() => {
    'protocol': 1,
    'device': 'amoled-1cdbd448ed24',
    'version': '0.2.0-amoled',
    'elfSha256': List.filled(64, 'a').join(),
    'boot': List.filled(32, 'b').join(),
    'imageState': 2,
  };
  test('legacy board keeps OTA compatibility', () {
    expect(
      BoardInfo.parse(utf8.encode(jsonEncode(info()))).otaSupported,
      isTrue,
    );
  });
  test('AMOLED control-only board reports USB maintenance explicitly', () {
    final value = info()
      ..addAll({
        'boardModel': 'esp32-s3-touch-amoled-2.16',
        'otaSupported': false,
      });
    final board = BoardInfo.parse(utf8.encode(jsonEncode(value)));
    expect(board.otaSupported, isFalse);
    expect(board.boardModel, 'esp32-s3-touch-amoled-2.16');
  });
}
