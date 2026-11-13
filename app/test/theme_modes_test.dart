import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/theme.dart';

void main() {
  test('approved semantic palette is exact in both appearances', () {
    final light = AppTheme.light(), dark = AppTheme.build();
    expect(light.colorScheme.primary, const Color(0xFF1764D9));
    expect(light.scaffoldBackgroundColor, const Color(0xFFF3F5F9));
    expect(light.cardTheme.color, Colors.white);
    expect(light.colorScheme.onSurface, const Color(0xFF18263A));
    expect(light.colorScheme.onSurfaceVariant, const Color(0xFF59677A));
    expect(dark.scaffoldBackgroundColor, const Color(0xFF101925));
    expect(dark.cardTheme.color, const Color(0xFF1C2939));
    expect(dark.colorScheme.primary, const Color(0xFFA5C8FF));
  });

  test('system theme has distinct readable light and dark surfaces', () {
    final light = AppTheme.light();
    final dark = AppTheme.build();
    expect(light.brightness, Brightness.light);
    expect(dark.brightness, Brightness.dark);
    expect(light.colorScheme.onSurface.computeLuminance(),
        lessThan(light.colorScheme.surface.computeLuminance()));
    expect(dark.colorScheme.onSurface.computeLuminance(),
        greaterThan(dark.colorScheme.surface.computeLuminance()));
  });
}
