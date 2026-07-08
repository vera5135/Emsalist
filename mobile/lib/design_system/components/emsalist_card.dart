import 'package:flutter/material.dart';

import '../../core/constants/app_constants.dart';

class EmsalistCard extends StatelessWidget {
  const EmsalistCard({
    super.key,
    required this.child,
    this.color,
    this.padding = const EdgeInsets.all(AppConstants.spacingMd),
    this.margin = EdgeInsets.zero,
    this.onTap,
    this.borderColor,
    this.semanticsLabel,
  });

  final Widget child;
  final Color? color;
  final EdgeInsetsGeometry padding;
  final EdgeInsetsGeometry margin;
  final VoidCallback? onTap;
  final Color? borderColor;
  final String? semanticsLabel;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final BorderRadius radius =
        BorderRadius.circular(AppConstants.radiusLg);

    Widget content = Container(
      padding: padding,
      decoration: BoxDecoration(
        color: color ?? theme.colorScheme.surface,
        borderRadius: radius,
        border: borderColor != null
            ? Border.all(color: borderColor!)
            : Border.all(color: theme.colorScheme.outlineVariant),
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: theme.shadowColor.withValues(alpha: 0.06),
            blurRadius: 8,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: child,
    );

    if (onTap != null) {
      content = Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: radius,
          onTap: onTap,
          child: content,
        ),
      );
    }

    content = Padding(padding: margin, child: content);

    if (semanticsLabel != null) {
      return Semantics(
        container: true,
        label: semanticsLabel,
        child: content,
      );
    }
    return content;
  }
}
