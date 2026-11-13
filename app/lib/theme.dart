import 'package:flutter/material.dart';

/// Material 3 Android themes with semantic colors for both system appearances.
class AppTheme {
  static AppColors colors(BuildContext context) =>
      AppColors(Theme.of(context).colorScheme);

  static ThemeData light() => _theme(Brightness.light);
  static ThemeData build() => _theme(Brightness.dark);

  static ThemeData _theme(Brightness brightness) {
    final dark = brightness == Brightness.dark;
    final background = Color(dark ? 0xFF101925 : 0xFFF3F5F9);
    final card = Color(dark ? 0xFF1C2939 : 0xFFFFFFFF);
    final ink = Color(dark ? 0xFFE5EBF5 : 0xFF18263A);
    final muted = Color(dark ? 0xFFB4C0D1 : 0xFF59677A);
    final blue = Color(dark ? 0xFFA5C8FF : 0xFF1764D9);
    final soft = Color(dark ? 0xFF213C60 : 0xFFEAF1FD);
    final onBlue = Color(dark ? 0xFF142D50 : 0xFFFFFFFF);
    final scheme = ColorScheme.fromSeed(
            seedColor: const Color(0xFF1764D9), brightness: brightness)
        .copyWith(
      primary: blue,
      onPrimary: onBlue,
      primaryContainer: soft,
      onPrimaryContainer: ink,
      secondary: blue,
      onSecondary: onBlue,
      secondaryContainer: soft,
      onSecondaryContainer: ink,
      tertiary: blue,
      onTertiary: onBlue,
      tertiaryContainer: soft,
      onTertiaryContainer: ink,
      surface: background,
      onSurface: ink,
      onSurfaceVariant: muted,
      surfaceContainerLowest: background,
      surfaceContainerLow: card,
      surfaceContainer: card,
      surfaceContainerHigh: soft,
      surfaceContainerHighest: Color(dark ? 0xFF253449 : 0xFFE5EAF2),
      surfaceBright: card,
      surfaceDim: background,
      surfaceTint: Colors.transparent,
      outline: Color(dark ? 0xFF50627B : 0xFFB7C4D7),
      outlineVariant: Color(dark ? 0xFF344254 : 0xFFDDE3ED),
      error: Color(dark ? 0xFFFFB2B8 : 0xFFB32B35),
      onError: Color(dark ? 0xFF3E242C : 0xFFFFFFFF),
      errorContainer: Color(dark ? 0xFF3E242C : 0xFFFFF0F0),
      onErrorContainer: Color(dark ? 0xFFFFC0C7 : 0xFF8F2430),
    );
    final base = ThemeData(
        useMaterial3: true,
        brightness: brightness,
        platform: TargetPlatform.android,
        colorScheme: scheme);
    return base.copyWith(
      scaffoldBackgroundColor: scheme.surfaceContainerLowest,
      appBarTheme: AppBarTheme(
          backgroundColor: scheme.surface,
          foregroundColor: scheme.onSurface,
          centerTitle: false),
      cardTheme: CardThemeData(
          color: scheme.surfaceContainerLow,
          elevation: 0,
          shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(20),
              side: BorderSide(color: scheme.outlineVariant))),
      filledButtonTheme: FilledButtonThemeData(
          style: FilledButton.styleFrom(
              minimumSize: const Size(48, 48),
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(14)),
              padding:
                  const EdgeInsets.symmetric(horizontal: 20, vertical: 14))),
      outlinedButtonTheme: OutlinedButtonThemeData(
          style: OutlinedButton.styleFrom(
              minimumSize: const Size(48, 48),
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(14)),
              padding:
                  const EdgeInsets.symmetric(horizontal: 20, vertical: 14))),
      inputDecorationTheme: InputDecorationTheme(
          filled: true,
          fillColor: scheme.surfaceContainerLow,
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
