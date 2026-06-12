import 'package:flutter/widgets.dart';

import 'stitch_tokens.dart';

abstract final class StitchLayout {
  static const minDesktopWidth = 980.0;
  static const maxContentWidth = 1440.0;
  static const leftRailWidth = 238.0;
  static const rightInspectorWidth = 294.0;
  static const statusBarHeight = 42.0;
  static const headerHeight = 94.0;

  static const pagePadding = EdgeInsets.all(StitchSpacing.lg);
  static const cardGap = SizedBox(width: StitchSpacing.md, height: StitchSpacing.md);

  static bool compact(BuildContext context) {
    return MediaQuery.sizeOf(context).width < minDesktopWidth;
  }
}

class StitchConstrained extends StatelessWidget {
  const StitchConstrained({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: StitchLayout.maxContentWidth),
        child: child,
      ),
    );
  }
}
