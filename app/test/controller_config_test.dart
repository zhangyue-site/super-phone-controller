import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/controller_config.dart';

void main() {
  test('unconfigured build exposes clear failure instead of a network fallback',
      () {
    expect(() => ControllerConfig.base, throwsStateError);
  }, skip: const bool.hasEnvironment('CONTROLLER_BASE_URL'));
  test('missing and unsafe service configuration fails without fallback', () {
    for (final value in [
      '',
      'http://controller.test',
      'https://user:secret@controller.invalid',
      'https://controller.test?token=secret',
      'https://controller.test#fragment'
    ]) {
      expect(() => ControllerConfig.validateBase(value), throwsStateError);
    }
  });
  test('explicit HTTPS service path is normalized', () {
    expect(ControllerConfig.validateBase('https://controller.test/api/'),
        'https://controller.test/api');
  });
}
