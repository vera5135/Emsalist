import 'package:flutter/material.dart';

import '../../../core/constants/app_constants.dart';
import '../../../design_system/components/emsalist_card.dart';

class DocumentCard extends StatelessWidget {
  const DocumentCard({
    super.key,
    required this.name,
    required this.size,
    this.status = 'uploaded',
    this.progress = 1.0,
  });

  final String name;
  final String size;
  final String status;
  final double progress;

  bool get _isUploading => status == 'uploading' && progress < 1.0;

  String get _statusLabel {
    switch (status) {
      case 'uploading':
        return 'Yükleniyor';
      case 'failed':
        return 'Başarısız';
      default:
        return 'Yüklendi';
    }
  }

  IconData get _fileIcon {
    final String lower = name.toLowerCase();
    if (lower.endsWith('.pdf')) {
      return Icons.picture_as_pdf_outlined;
    }
    if (lower.endsWith('.doc') || lower.endsWith('.docx')) {
      return Icons.description_outlined;
    }
    return Icons.insert_drive_file_outlined;
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return EmsalistCard(
      semanticsLabel: 'Belge: $name, boyut $size, durum $_statusLabel',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Icon(_fileIcon, color: theme.colorScheme.primary),
              const SizedBox(width: AppConstants.spacingMd),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      name,
                      style: theme.textTheme.titleSmall
                          ?.copyWith(fontWeight: FontWeight.w600),
                      overflow: TextOverflow.ellipsis,
                    ),
                    Text(
                      '$size • $_statusLabel',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ],
                ),
              ),
              if (!_isUploading)
                Icon(
                  status == 'failed'
                      ? Icons.error_outline
                      : Icons.check_circle_outline,
                  color: status == 'failed'
                      ? theme.colorScheme.error
                      : const Color(0xFF2E7D32),
                  size: 20,
                ),
            ],
          ),
          if (_isUploading) ...<Widget>[
            const SizedBox(height: AppConstants.spacingSm),
            ClipRRect(
              borderRadius: BorderRadius.circular(AppConstants.radiusSm),
              child: LinearProgressIndicator(value: progress),
            ),
          ],
        ],
      ),
    );
  }
}
