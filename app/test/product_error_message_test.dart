import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/product_widgets.dart';
void main() {
 test('nested exception class names are removed from user recovery guidance', () {
  expect(productError('连接未完成：FormatException: 屏幕共享授权失败，请重试'), '连接未完成：屏幕共享授权失败，请重试');
 });
}
