import 'package:flutter/material.dart';

abstract final class StitchColors {
  static const background = Color(0xFFFBFCF4);
  static const warmBackground = Color(0xFFEDF3E1);
  static const card = Color(0xFFFFFFFF);
  static const cardGlow = Color(0xFFFCFFF7);
  static const textPrimary = Color(0xFF1F2922);
  static const textSecondary = Color(0xFF303B33);
  static const textMuted = Color(0xFF607063);
  static const textFaint = Color(0xFF97A493);
  static const border = Color(0xFFD1DDCC);
  static const borderSoft = Color(0xFFDFEBD8);
  static const borderFaint = Color(0xFFEBF2E4);
  static const accent = Color(0xFF78A881);
  static const accentDeep = Color(0xFF477453);
  static const accentSoft = Color(0xFFDEEDDC);
  static const winner = Color(0xFFD6B85F);
  static const warning = Color(0xFFC77D78);
  static const warningSoft = Color(0xFFF9E4E0);
  static const shadow = Color(0x1A243527);
  static const logButton = Color(0xFF12452E);
}

abstract final class StitchSpacing {
  static const xs = 6.0;
  static const sm = 10.0;
  static const md = 16.0;
  static const lg = 22.0;
  static const xl = 32.0;
  static const xxl = 44.0;
}

abstract final class StitchRadius {
  static const sm = 10.0;
  static const md = 16.0;
  static const lg = 24.0;
  static const xl = 32.0;
}

abstract final class StitchShadow {
  static const card = [
    BoxShadow(
      color: StitchColors.shadow,
      blurRadius: 28,
      offset: Offset(0, 14),
    ),
  ];

  static const soft = [
    BoxShadow(
      color: Color(0x10243527),
      blurRadius: 18,
      offset: Offset(0, 8),
    ),
  ];
}

abstract final class StitchTextStyles {
  static const eyebrow = TextStyle(
    fontSize: 12,
    fontWeight: FontWeight.w700,
    letterSpacing: 0.5,
    color: StitchColors.accentDeep,
  );

  static const pageTitle = TextStyle(
    fontSize: 34,
    height: 1.12,
    fontWeight: FontWeight.w800,
    color: StitchColors.textPrimary,
  );

  static const brandTitle = TextStyle(
    fontSize: 22,
    fontWeight: FontWeight.w900,
    color: StitchColors.textPrimary,
  );

  static const sectionTitle = TextStyle(
    fontSize: 18,
    fontWeight: FontWeight.w800,
    color: StitchColors.textPrimary,
  );

  static const body = TextStyle(
    fontSize: 14,
    height: 1.45,
    color: StitchColors.textSecondary,
  );

  static const muted = TextStyle(
    fontSize: 13,
    height: 1.45,
    color: StitchColors.textMuted,
  );
}
