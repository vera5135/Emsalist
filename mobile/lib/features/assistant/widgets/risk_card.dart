import 'package:flutter/material.dart';

import '../../../core/constants/app_constants.dart';
import '../../../design_system/components/emsalist_card.dart';

enum RiskSeverity {
  low,
  medium,
  high;

  static RiskSeverity fromString(String value) {
    switch (value) {
      case 'high':
        return RiskSeverity.high;
      case 'medium':
        return RiskSeverity.medium;
      default:
        return RiskSeverity.low;
    }
  }

  String get label {
    switch (this) {
      case RiskSeverity.low:
        return 'Düşük Risk';
      case RiskSeverity.medium:
        return 'Orta Risk';
      case RiskSeverity.high:
        return 'Yüksek Risk';
    }
  }

  Color get color {
    switch (this) {
      case RiskSeverity.low:
        return const Color(0xFF2E7D32);
      case RiskSeverity.medium:
        return const Color(0xFFF9A825);
      case RiskSeverity.high:
        return const Color(0xFFC62828);
    }
  }

  IconData get icon {
    switch (this) {
      case RiskSeverity.low:
        return Icons.info_outline;
      case RiskSeverity.medium:
        return Icons.warning_amber_outlined;
      case RiskSeverity.high:
        return Icons.dangerous_outlined;
    }
  }
}

class RiskCard extends StatelessWidget {
  const RiskCard({
    super.key,
    required this.title,
    required this.description,
    this.severity = RiskSeverity.medium,
  });

  final String title;
  final String description;
  final RiskSeverity severity;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return EmsalistCard(
      color: severity.color.withValues(alpha: 0.06),
      borderColor: severity.color.withValues(alpha: 0.4),
      semanticsLabel: '${severity.label}: $title. $description',
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Icon(severity.icon, color: severity.color),
          const SizedBox(width: AppConstants.spacingMd),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Row(
                  children: <Widget>[
                    Expanded(
                      child: Text(
                        title,
                        style: theme.textTheme.titleSmall?.copyWith(
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                    Text(
                      severity.label,
                      style: theme.textTheme.labelSmall?.copyWith(
                        color: severity.color,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: AppConstants.spacingXs),
                Text(description, style: theme.textTheme.bodyMedium),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
