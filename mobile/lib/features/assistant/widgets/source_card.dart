import 'package:flutter/material.dart';

import '../../../core/constants/app_constants.dart';
import '../../../design_system/components/emsalist_card.dart';

class SourceCard extends StatelessWidget {
  const SourceCard({
    super.key,
    required this.title,
    required this.sourceType,
    this.verified = false,
    this.relevance = 0.0,
  });

  final String title;
  final String sourceType;
  final bool verified;
  final double relevance;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final int relevancePct = (relevance * 100).round();
    return EmsalistCard(
      semanticsLabel:
          'Kaynak: $title, tür $sourceType, ${verified ? 'doğrulandı' : 'doğrulanmadı'}, ilgi yüzde $relevancePct',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Icon(
                Icons.menu_book_outlined,
                size: 20,
                color: theme.colorScheme.primary,
              ),
              const SizedBox(width: AppConstants.spacingSm),
              Expanded(
                child: Text(
                  title,
                  style: theme.textTheme.titleSmall
                      ?.copyWith(fontWeight: FontWeight.w600),
                ),
              ),
            ],
          ),
          const SizedBox(height: AppConstants.spacingSm),
          Wrap(
            spacing: AppConstants.spacingSm,
            runSpacing: AppConstants.spacingXs,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: <Widget>[
              _Badge(label: sourceType, color: theme.colorScheme.primary),
              _Badge(
                label: verified ? 'Doğrulandı' : 'Doğrulanmadı',
                color: verified
                    ? const Color(0xFF2E7D32)
                    : theme.colorScheme.outline,
                icon: verified ? Icons.verified_outlined : Icons.help_outline,
              ),
              Text(
                'İlgi: %$relevancePct',
                style: theme.textTheme.bodySmall,
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _Badge extends StatelessWidget {
  const _Badge({required this.label, required this.color, this.icon});

  final String label;
  final Color color;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppConstants.spacingSm,
        vertical: 2,
      ),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(AppConstants.radiusSm),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          if (icon != null) ...<Widget>[
            Icon(icon, size: 14, color: color),
            const SizedBox(width: 4),
          ],
          Text(
            label,
            style: Theme.of(context)
                .textTheme
                .labelSmall
                ?.copyWith(color: color, fontWeight: FontWeight.w600),
          ),
        ],
      ),
    );
  }
}
