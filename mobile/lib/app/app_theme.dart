import 'package:flutter/material.dart';

class AppColors {
  const AppColors._();

  static const Color primary = Color(0xFF475569);
  static const Color primaryDark = Color(0xFF94A3B8);

  static const Color surfaceLight = Color(0xFFFFFFFF);
  static const Color backgroundLight = Color(0xFFF8FAFC);
  static const Color surfaceDark = Color(0xFF1E1E1E);
  static const Color backgroundDark = Color(0xFF121212);

  static const Color error = Color(0xFFC62828);
}

class AppSpacing {
  const AppSpacing._();

  static const double xs = 4;
  static const double sm = 8;
  static const double md = 16;
  static const double lg = 24;
  static const double xl = 32;
}

class AppTheme {
  const AppTheme._();

  static ThemeData get light => _build(Brightness.light);
  static ThemeData get dark => _build(Brightness.dark);

  static ThemeData _build(Brightness brightness) {
    final bool isDark = brightness == Brightness.dark;
    final ColorScheme scheme = ColorScheme.fromSeed(
      seedColor: AppColors.primary,
      brightness: brightness,
      surface: isDark ? AppColors.surfaceDark : AppColors.surfaceLight,
      error: AppColors.error,
    );

    final TextTheme textTheme = Typography.material2021(
      platform: TargetPlatform.iOS,
    ).black.apply(
          bodyColor: scheme.onSurface,
          displayColor: scheme.onSurface,
        );

    return ThemeData(
      useMaterial3: true,
      brightness: brightness,
      colorScheme: scheme,
      scaffoldBackgroundColor:
          isDark ? AppColors.backgroundDark : AppColors.backgroundLight,
      textTheme: isDark
          ? textTheme.apply(
              bodyColor: scheme.onSurface,
              displayColor: scheme.onSurface,
            )
          : textTheme,
      appBarTheme: AppBarTheme(
        centerTitle: false,
        elevation: 0,
        scrolledUnderElevation: 1,
        backgroundColor: scheme.surface,
        foregroundColor: scheme.onSurface,
      ),
      dividerTheme: DividerThemeData(
        color: scheme.outlineVariant,
        space: 1,
        thickness: 1,
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppSpacing.md),
          ),
        ),
      ),
      snackBarTheme: SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppSpacing.sm),
        ),
      ),
    );
  }
}
