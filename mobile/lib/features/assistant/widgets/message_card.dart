import 'package:flutter/material.dart';

import '../../../core/constants/app_constants.dart';
import '../../../core/models/message_model.dart';
import 'document_card.dart';
import 'missing_info_card.dart';
import 'risk_card.dart';
import 'source_card.dart';

class MessageCard extends StatelessWidget {
  const MessageCard({super.key, required this.message});

  final MessageModel message;

  @override
  Widget build(BuildContext context) {
    final bool isUser = message.isUser;
    final Alignment alignment = isUser
        ? Alignment.centerRight
        : Alignment.centerLeft;

    Widget content;
    if (message.type == MessageType.card) {
      content = _buildCard(message);
    } else {
      content = _TextBubble(message: message);
    }

    return Align(
      alignment: alignment,
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxWidth: MediaQuery.sizeOf(context).width * 0.85,
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(
            horizontal: AppConstants.spacingMd,
            vertical: AppConstants.spacingXs,
          ),
          child: content,
        ),
      ),
    );
  }

  Widget _buildCard(MessageModel message) {
    final Map<String, Object?> data = message.cardData;
    switch (message.cardSubtype) {
      case CardSubtype.missingInfo:
        return MissingInfoCard(
          description: (data['description'] as String?) ?? '',
        );
      case CardSubtype.source:
        return SourceCard(
          title: (data['title'] as String?) ?? '',
          sourceType: (data['sourceType'] as String?) ?? '',
          verified: (data['verified'] as bool?) ?? false,
          relevance: (data['relevance'] as num?)?.toDouble() ?? 0.0,
        );
      case CardSubtype.risk:
        return RiskCard(
          title: (data['title'] as String?) ?? '',
          description: (data['description'] as String?) ?? '',
          severity: RiskSeverity.fromString(
            (data['severity'] as String?) ?? 'medium',
          ),
        );
      case CardSubtype.document:
        return DocumentCard(
          name: (data['name'] as String?) ?? '',
          size: (data['size'] as String?) ?? '',
          status: (data['status'] as String?) ?? 'uploaded',
          progress: (data['progress'] as num?)?.toDouble() ?? 1.0,
        );
      case null:
        return const SizedBox.shrink();
    }
  }
}

class _TextBubble extends StatelessWidget {
  const _TextBubble({required this.message});

  final MessageModel message;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final bool isUser = message.isUser;
    final Color bg = isUser
        ? theme.colorScheme.primary
        : theme.colorScheme.surfaceContainerHighest;
    final Color fg = isUser
        ? theme.colorScheme.onPrimary
        : theme.colorScheme.onSurface;

    return Semantics(
      label: isUser ? 'Sen: ${message.text}' : 'Asistan: ${message.text}',
      child: Container(
        padding: const EdgeInsets.symmetric(
          horizontal: AppConstants.spacingMd,
          vertical: AppConstants.spacingSm + 2,
        ),
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.only(
            topLeft: const Radius.circular(AppConstants.radiusLg),
            topRight: const Radius.circular(AppConstants.radiusLg),
            bottomLeft: Radius.circular(
              isUser ? AppConstants.radiusLg : AppConstants.radiusSm,
            ),
            bottomRight: Radius.circular(
              isUser ? AppConstants.radiusSm : AppConstants.radiusLg,
            ),
          ),
        ),
        child: Text(
          message.text,
          style: theme.textTheme.bodyMedium?.copyWith(color: fg),
        ),
      ),
    );
  }
}
