import 'package:flutter/material.dart';

/// Material 3 Android themes with semantic colors for both system appearances.
class AppTheme {
  static AppColors colors(BuildContext context) =>
      AppColors(Theme.of(context).colorScheme);

  static ThemeData light() => _theme(Brightness.light);
  static ThemeData build() => _theme(Brightness.dark);

  static ThemeData _theme(Brightness brightness) {
    final scheme = ColorScheme.fromSeed(
        seedColor: const Color(0xFF1764D9), brightness: brightness);
    final base = ThemeData(
        useMaterial3: true,
        brightness: brightness,
        platform: TargetPlatform.android,
        colorScheme: scheme);
    return base.copyWith(
      scaffoldBackgroundColor: scheme.surface,
      appBarTheme: AppBarTheme(
          backgroundColor: scheme.surface,
          foregroundColor: scheme.onSurface,
          centerTitle: false),
      cardTheme: CardThemeData(
          color: scheme.surfaceContainerLow,
          elevation: 0,
          shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(16),
              side: BorderSide(color: scheme.outlineVariant))),
      filledButtonTheme: FilledButtonThemeData(
          style: FilledButton.styleFrom(
              minimumSize: const Size(48, 48),
              padding:
                  const EdgeInsets.symmetric(horizontal: 20, vertical: 14))),
      outlinedButtonTheme: OutlinedButtonThemeData(
          style: OutlinedButton.styleFrom(
              minimumSize: const Size(48, 48),
              padding:
                  const EdgeInsets.symmetric(horizontal: 20, vertical: 14))),
      inputDecorationTheme: InputDecorationTheme(
          filled: true,
          fillColor: scheme.surfaceContainerHighest,
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(12))),
      dividerTheme: DividerThemeData(color: scheme.outlineVariant),
    );
  }

  /// 等宽字体样式，用于版本号、sha256、字节数这类"要看清"的内容。
  static const mono = TextStyle(
    fontFamily: 'monospace',
    fontFeatures: [FontFeature.tabularFigures()],
  );
}

/// Semantic component colors derived from the active Material color scheme.
class AppColors {
  final ColorScheme scheme;
  const AppColors(this.scheme);
  Color get bg => scheme.surface;
  Color get surface => scheme.surfaceContainerLow;
  Color get surfaceHi => scheme.surfaceContainerHighest;
  Color get accent => scheme.primary;
  Color get accentDim => scheme.secondary;
  Color get danger => scheme.error;
  Color get warn => scheme.brightness == Brightness.dark
      ? const Color(0xFFFFD180)
      : const Color(0xFF795500);
  Color get text => scheme.onSurface;
  Color get textDim => scheme.onSurfaceVariant;
  Color get border => scheme.outlineVariant;
  Color get onAccent => scheme.onPrimary;
}
