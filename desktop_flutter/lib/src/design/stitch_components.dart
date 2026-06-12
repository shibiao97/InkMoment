import 'package:flutter/material.dart';

import 'stitch_tokens.dart';

class StitchScaffold extends StatelessWidget {
  const StitchScaffold({super.key, required this.child, this.padding});

  final Widget child;
  final EdgeInsetsGeometry? padding;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [StitchColors.background, StitchColors.warmBackground],
        ),
      ),
      child: Padding(
        padding: padding ?? const EdgeInsets.all(StitchSpacing.lg),
        child: child,
      ),
    );
  }
}

class StitchCard extends StatelessWidget {
  const StitchCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(StitchSpacing.lg),
    this.backgroundColor = StitchColors.card,
    this.borderColor = StitchColors.borderSoft,
    this.radius = StitchRadius.lg,
    this.shadows = StitchShadow.soft,
  });

  final Widget child;
  final EdgeInsetsGeometry padding;
  final Color backgroundColor;
  final Color borderColor;
  final double radius;
  final List<BoxShadow> shadows;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: padding,
      decoration: BoxDecoration(
        color: backgroundColor,
        borderRadius: BorderRadius.circular(radius),
        border: Border.all(color: borderColor),
        boxShadow: shadows,
      ),
      child: child,
    );
  }
}

class StitchSectionHeader extends StatelessWidget {
  const StitchSectionHeader({
    super.key,
    required this.title,
    this.eyebrow,
    this.description,
    this.trailing,
  });

  final String title;
  final String? eyebrow;
  final String? description;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (eyebrow != null) ...[
                Text(eyebrow!, style: StitchTextStyles.eyebrow),
                const SizedBox(height: StitchSpacing.xs),
              ],
              Text(title, style: StitchTextStyles.pageTitle),
              if (description != null) ...[
                const SizedBox(height: StitchSpacing.sm),
                Text(description!, style: StitchTextStyles.muted),
              ],
            ],
          ),
        ),
        if (trailing != null) ...[
          const SizedBox(width: StitchSpacing.md),
          trailing!,
        ],
      ],
    );
  }
}

class StitchPill extends StatelessWidget {
  const StitchPill({
    super.key,
    required this.label,
    this.value,
    this.selected = false,
    this.color,
  });

  final String label;
  final String? value;
  final bool selected;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final tone = color ?? (selected ? StitchColors.accentDeep : StitchColors.textMuted);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: selected ? StitchColors.accentSoft : StitchColors.cardGlow,
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: selected ? StitchColors.accent : StitchColors.borderSoft),
      ),
      child: value == null
          ? Text(
              label,
              style: TextStyle(color: tone, fontWeight: FontWeight.w700, fontSize: 12),
            )
          : Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(label, style: const TextStyle(color: StitchColors.textMuted, fontSize: 11)),
                Text(
                  value!,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(color: tone, fontWeight: FontWeight.w800, fontSize: 13),
                ),
              ],
            ),
    );
  }
}

class StitchMetricCard extends StatelessWidget {
  const StitchMetricCard({
    super.key,
    required this.label,
    required this.value,
    this.accent = StitchColors.accentDeep,
  });

  final String label;
  final String value;
  final Color accent;

  @override
  Widget build(BuildContext context) {
    return StitchCard(
      padding: const EdgeInsets.all(StitchSpacing.md),
      shadows: const [],
      backgroundColor: StitchColors.cardGlow,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(label, style: StitchTextStyles.muted),
          const SizedBox(height: StitchSpacing.xs),
          Text(
            value,
            style: TextStyle(fontSize: 24, fontWeight: FontWeight.w800, color: accent),
          ),
        ],
      ),
    );
  }
}

class StitchEmptyState extends StatelessWidget {
  const StitchEmptyState({super.key, required this.message, this.icon});

  final String message;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon ?? Icons.photo_library_outlined, color: StitchColors.textFaint, size: 42),
          const SizedBox(height: StitchSpacing.sm),
          Text(message, textAlign: TextAlign.center, style: StitchTextStyles.muted),
        ],
      ),
    );
  }
}

class StitchPhotoFrame extends StatelessWidget {
  const StitchPhotoFrame({
    super.key,
    required this.child,
    this.aspectRatio,
    this.padding = const EdgeInsets.all(6),
  });

  final Widget child;
  final double? aspectRatio;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) {
    final framed = Container(
      padding: padding,
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(StitchRadius.md),
        border: Border.all(color: StitchColors.borderSoft),
        boxShadow: StitchShadow.soft,
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(StitchRadius.sm),
        child: ColoredBox(color: StitchColors.warmBackground, child: child),
      ),
    );
    if (aspectRatio == null) return framed;
    return AspectRatio(aspectRatio: aspectRatio!, child: framed);
  }
}

class StitchProgressBar extends StatelessWidget {
  const StitchProgressBar({super.key, required this.value});

  final double value;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(999),
      child: LinearProgressIndicator(
        minHeight: 12,
        value: value,
        backgroundColor: StitchColors.accentSoft,
        valueColor: const AlwaysStoppedAnimation<Color>(StitchColors.accentDeep),
      ),
    );
  }
}

class StitchWarning extends StatelessWidget {
  const StitchWarning({super.key, required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(StitchSpacing.md),
      decoration: BoxDecoration(
        color: StitchColors.warningSoft,
        borderRadius: BorderRadius.circular(StitchRadius.md),
        border: Border.all(color: StitchColors.warning.withValues(alpha: 0.28)),
      ),
      child: Text(message, style: const TextStyle(color: StitchColors.warning)),
    );
  }
}
