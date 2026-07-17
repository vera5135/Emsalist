import 'package:flutter/material.dart';

import '../../../core/constants/app_constants.dart';
import '../domain/draft_item.dart';

const List<Map<String, String>> _reasonCodes = <Map<String, String>>[
  <String, String>{'code': 'legal_error', 'label': 'Hukuki hata'},
  <String, String>{'code': 'factual_error', 'label': 'Maddi hata'},
  <String, String>{'code': 'formatting', 'label': 'Biçimlendirme'},
  <String, String>{'code': 'missing_reference', 'label': 'Eksik atıf'},
  <String, String>{'code': 'tone_language', 'label': 'Üslup / Dil'},
  <String, String>{'code': 'insufficient_support', 'label': 'Yetersiz dayanak'},
  <String, String>{'code': 'irrelevant_content', 'label': 'İlgisiz içerik'},
  <String, String>{'code': 'other', 'label': 'Diğer'},
];

void showRequestChangesSheet(
  BuildContext context, {
  required void Function(String reasonCode) onConfirm,
}) {
  showModalBottomSheet<void>(
    context: context,
    useSafeArea: true,
    builder: (BuildContext sheetContext) {
      String selectedCode = 'other';
      return StatefulBuilder(
        builder: (BuildContext ctx, StateSetter setSheetState) {
          return SafeArea(
            child: Padding(
              padding: const EdgeInsets.all(AppConstants.spacingMd),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: <Widget>[
                  Text(
                    'Değişiklik Talebi Nedeni',
                    style: Theme.of(ctx).textTheme.titleLarge,
                  ),
                  const SizedBox(height: AppConstants.spacingMd),
                  RadioGroup<String>(
                    groupValue: selectedCode,
                    onChanged: (String? value) {
                      if (value != null) {
                        setSheetState(() => selectedCode = value);
                        Navigator.of(sheetContext).pop();
                        onConfirm(selectedCode);
                      }
                    },
                    child: Column(
                      children: _reasonCodes.map((Map<String, String> rc) {
                        final String code = rc['code']!;
                        final String label = rc['label']!;
                        return RadioListTile<String>(
                          title: Text(label),
                          value: code,
                          dense: true,
                          contentPadding: EdgeInsets.zero,
                        );
                      }).toList(),
                    ),
                  ),
                  const SizedBox(height: AppConstants.spacingMd),
                ],
              ),
            ),
          );
        },
      );
    },
  );
}

void showRevisionHistorySheet(
  BuildContext context, {
  required List<DraftRevisionItem> revisions,
  required DraftParagraphItem currentParagraph,
  required Future<void> Function(String revisionId) onRestore,
}) {
  showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    useSafeArea: true,
    builder: (BuildContext sheetContext) {
      final ThemeData theme = Theme.of(sheetContext);
      return DraggableScrollableSheet(
        initialChildSize: 0.7,
        minChildSize: 0.4,
        maxChildSize: 0.95,
        expand: false,
        builder: (BuildContext ctx, ScrollController scrollController) {
          return Column(
            children: <Widget>[
              Padding(
                padding: const EdgeInsets.all(AppConstants.spacingMd),
                child: Row(
                  children: <Widget>[
                    Expanded(
                      child: Text(
                        'Geçmiş Sürümler — ${currentParagraph.label}',
                        style: theme.textTheme.titleLarge,
                      ),
                    ),
                    IconButton(
                      icon: const Icon(Icons.close),
                      onPressed: () => Navigator.of(sheetContext).pop(),
                    ),
                  ],
                ),
              ),
              const Divider(height: 1),
              Expanded(
                child: ListView.builder(
                  controller: scrollController,
                  itemCount: revisions.length,
                  itemBuilder: (BuildContext ctx, int index) {
                    final DraftRevisionItem rev = revisions[index];
                    final bool isCurrent = rev.currentRevision;
                    return _RevisionTile(
                      revision: rev,
                      isCurrent: isCurrent,
                      theme: theme,
                      onRestore: () => _confirmRestore(
                        sheetContext,
                        rev.id,
                        rev.revisionNumber,
                        onRestore,
                      ),
                    );
                  },
                ),
              ),
            ],
          );
        },
      );
    },
  );
}

class _RevisionTile extends StatefulWidget {
  const _RevisionTile({
    required this.revision,
    required this.isCurrent,
    required this.theme,
    required this.onRestore,
  });

  final DraftRevisionItem revision;
  final bool isCurrent;
  final ThemeData theme;
  final VoidCallback onRestore;

  @override
  State<_RevisionTile> createState() => _RevisionTileState();
}

class _RevisionTileState extends State<_RevisionTile> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    final DraftRevisionItem rev = widget.revision;
    final ThemeData theme = widget.theme;

    return Card(
      margin: const EdgeInsets.symmetric(
        horizontal: AppConstants.spacingSm,
        vertical: AppConstants.spacingXs,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          ListTile(
            title: Row(
              children: <Widget>[
                Text('Sürüm ${rev.revisionNumber}'),
                const SizedBox(width: AppConstants.spacingSm),
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: AppConstants.spacingSm,
                    vertical: 2,
                  ),
                  decoration: BoxDecoration(
                    color: theme.colorScheme.primaryContainer,
                    borderRadius: BorderRadius.circular(AppConstants.radiusSm),
                  ),
                  child: Text(rev.label, style: theme.textTheme.labelSmall),
                ),
                if (widget.isCurrent) ...<Widget>[
                  const SizedBox(width: AppConstants.spacingSm),
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: AppConstants.spacingSm,
                      vertical: 2,
                    ),
                    decoration: BoxDecoration(
                      color: theme.colorScheme.tertiaryContainer,
                      borderRadius: BorderRadius.circular(
                        AppConstants.radiusSm,
                      ),
                    ),
                    child: Text('Güncel', style: theme.textTheme.labelSmall),
                  ),
                ],
              ],
            ),
            subtitle: Text(_formatDateTime(rev.createdAt)),
            trailing: IconButton(
              icon: Icon(_expanded ? Icons.expand_less : Icons.expand_more),
              tooltip: _expanded ? 'Küçült' : 'Genişlet',
              onPressed: () => setState(() => _expanded = !_expanded),
            ),
          ),
          if (_expanded) ...<Widget>[
            const Divider(height: 1),
            Padding(
              padding: const EdgeInsets.all(AppConstants.spacingMd),
              child: SelectableText(rev.text),
            ),
            if (!widget.isCurrent)
              SizedBox(
                width: double.infinity,
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(
                    AppConstants.spacingSm,
                    0,
                    AppConstants.spacingSm,
                    AppConstants.spacingSm,
                  ),
                  child: Semantics(
                    button: true,
                    label: 'Bu sürüme dön',
                    child: OutlinedButton(
                      onPressed: widget.onRestore,
                      child: const Text('Bu sürüme dön'),
                    ),
                  ),
                ),
              ),
          ],
        ],
      ),
    );
  }

  String _formatDateTime(String isoString) {
    try {
      final DateTime dt = DateTime.parse(isoString).toLocal();
      return '${dt.day.toString().padLeft(2, '0')}.${dt.month.toString().padLeft(2, '0')}.${dt.year} ${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
    } on Object {
      return isoString;
    }
  }
}

void _confirmRestore(
  BuildContext context,
  String revisionId,
  int revisionNumber,
  Future<void> Function(String revisionId) onRestore,
) {
  showDialog<void>(
    context: context,
    builder: (BuildContext dialogContext) {
      return AlertDialog(
        title: const Text('Sürüme dön'),
        content: Text(
          '$revisionNumber numaralı sürüme dönmek istediğinize emin misiniz? Mevcut içerik kaybolacaktır.',
        ),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(),
            child: const Text('İptal'),
          ),
          FilledButton(
            onPressed: () {
              Navigator.of(dialogContext).pop();
              onRestore(revisionId);
            },
            child: const Text('Dön'),
          ),
        ],
      );
    },
  );
}
