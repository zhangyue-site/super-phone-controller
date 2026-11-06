import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/theme.dart';

void main() {
  test('system theme has distinct readable light and dark surfaces', () {
    final light = AppTheme.light();
    final dark = AppTheme.build();
    expect(light.brightness, Brightness.light);
    expect(dark.brightness, Brightness.dark);
    expect(light.colorScheme.onSurface.computeLuminance(), lessThan(light.colorScheme.surface.computeLuminance()));
    expect(dark.colorScheme.onSurface.computeLuminance(), greaterThan(dark.colorScheme.surface.computeLuminance()));
  });
}
