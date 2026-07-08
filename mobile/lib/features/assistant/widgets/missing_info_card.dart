import 'package:flutter/material.dart';

import '../../../core/constants/app_constants.dart';
import '../../../design_system/components/emsalist_card.dart';

class MissingInfoCard extends StatelessWidget {
  const MissingInfoCard({super.key, required this.description});

  final String description;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    const Color accent = Color(0xFFC62828);
    return EmsalistCard(
      color: accent.withValues(alpha: 0.06),
      borderColor: accent.withValues(alpha: 0.4),
      semanticsLabel: 'Eksik bilgi: $description',
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const Icon(Icons.help_outline, color: accent),
          const SizedBox(width: AppConstants.spacingMd),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  'Eksik Bilgi',
                  style: theme.textTheme.titleSmall?.copyWith(
                    color: accent,
                    fontWeight: FontWeight.w600,
                  ),
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
