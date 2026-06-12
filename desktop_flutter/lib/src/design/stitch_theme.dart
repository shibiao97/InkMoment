import 'package:flutter/material.dart';

import 'stitch_tokens.dart';

ThemeData buildStitchTheme() {
  final colorScheme = ColorScheme.fromSeed(
    seedColor: StitchColors.accent,
    brightness: Brightness.light,
    primary: StitchColors.accentDeep,
    secondary: StitchColors.accent,
    surface: StitchColors.card,
    error: StitchColors.warning,
  );

  final base = ThemeData(
    useMaterial3: true,
    brightness: Brightness.light,
    colorScheme: colorScheme,
    scaffoldBackgroundColor: StitchColors.background,
    fontFamily: 'PingFang SC',
  );

  return base.copyWith(
    textTheme: base.textTheme.apply(
      bodyColor: StitchColors.textPrimary,
      displayColor: StitchColors.textPrimary,
    ),
    cardTheme: CardThemeData(
      color: StitchColors.card,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(StitchRadius.lg),
        side: const BorderSide(color: StitchColors.borderSoft),
      ),
      margin: EdgeInsets.zero,
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: StitchColors.accentDeep,
        foregroundColor: Colors.white,
        disabledBackgroundColor: StitchColors.borderSoft,
        disabledForegroundColor: StitchColors.textFaint,
        padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 16),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(StitchRadius.md),
        ),
        textStyle: const TextStyle(fontWeight: FontWeight.w700),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: StitchColors.accentDeep,
        side: const BorderSide(color: StitchColors.border),
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 15),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(StitchRadius.md),
        ),
        textStyle: const TextStyle(fontWeight: FontWeight.w700),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: StitchColors.cardGlow,
      labelStyle: const TextStyle(color: StitchColors.textMuted),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(StitchRadius.md),
        borderSide: const BorderSide(color: StitchColors.borderSoft),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(StitchRadius.md),
        borderSide: const BorderSide(color: StitchColors.borderSoft),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(StitchRadius.md),
        borderSide: const BorderSide(color: StitchColors.accentDeep, width: 1.4),
      ),
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 15),
    ),
    chipTheme: base.chipTheme.copyWith(
      backgroundColor: StitchColors.cardGlow,
      selectedColor: StitchColors.accentSoft,
      labelStyle: const TextStyle(color: StitchColors.textSecondary),
      side: const BorderSide(color: StitchColors.borderSoft),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(StitchRadius.md),
      ),
    ),
    sliderTheme: base.sliderTheme.copyWith(
      activeTrackColor: StitchColors.accentDeep,
      inactiveTrackColor: StitchColors.accentSoft,
      thumbColor: StitchColors.accentDeep,
      overlayColor: StitchColors.accent.withValues(alpha: 0.14),
    ),
    dropdownMenuTheme: DropdownMenuThemeData(
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: StitchColors.cardGlow,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(StitchRadius.md),
        ),
      ),
    ),
  );
}
