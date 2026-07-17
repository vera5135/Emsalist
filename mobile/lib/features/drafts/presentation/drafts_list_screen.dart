import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/constants/app_constants.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/widgets/state_widgets.dart';
import '../application/draft_providers.dart';
import '../domain/draft_item.dart';

class DraftsListScreen extends ConsumerWidget {
  const DraftsListScreen({required this.caseId, super.key});

  final String caseId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final AsyncValue<List<DraftItem>> drafts = ref.watch(
      caseDraftsProvider(caseId),
    );

    return Scaffold(
      appBar: AppBar(title: const Text('Taslaklar')),
      body: drafts.when(
        loading: () => const LoadingWidget(message: 'Taslaklar yükleniyor'),
        error: (Object error, _) => AppErrorWidget(
          message: error is ApiException
              ? error.message
              : 'Taslaklar yüklenemedi.',
          onRetry: () => ref.invalidate(caseDraftsProvider(caseId)),
        ),
        data: (List<DraftItem> items) {
          if (items.isEmpty) {
            return const EmptyWidget(
              title: 'Henüz taslak yok',
              message: 'Yeni bir taslak oluşturarak başlayın.',
              icon: Icons.description_outlined,
            );
          }
          return RefreshIndicator(
            onRefresh: () async {
              ref.invalidate(caseDraftsProvider(caseId));
              await ref.read(caseDraftsProvider(caseId).future);
            },
            child: ListView.builder(
              itemCount: items.length,
              itemBuilder: (BuildContext context, int index) {
                final DraftItem draft = items[index];
                return _DraftListCard(
                  draft: draft,
                  onTap: () =>
                      context.push('/cases/$caseId/drafts/${draft.id}'),
                );
              },
            ),
          );
        },
      ),
      floatingActionButton: FloatingActionButton.extended(
        heroTag: 'new_draft_fab',
        label: const Text('Yeni Taslak'),
        icon: const Icon(Icons.add),
        onPressed: () => _showCreateDraftSheet(context, ref, caseId),
      ),
    );
  }
}

class _DraftListCard extends StatelessWidget {
  const _DraftListCard({required this.draft, required this.onTap});

  final DraftItem draft;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Card(
      child: ListTile(
        title: Text(draft.title),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            const SizedBox(height: AppConstants.spacingXs),
            Row(
              children: <Widget>[
                _StatusBadge(status: draft.status),
                const SizedBox(width: AppConstants.spacingSm),
                Text(
                  draft.label,
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
              ],
            ),
            const SizedBox(height: AppConstants.spacingXs),
            Text(
              'Paragraf: ${draft.paragraphCount}  ·  Sürüm: ${draft.version}  ·  ${_formatDateTime(draft.updatedAt)}',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ),
        trailing: const Icon(Icons.chevron_right),
        onTap: onTap,
      ),
    );
  }

  String _formatDateTime(String isoString) {
    try {
      final DateTime dt = DateTime.parse(isoString).toLocal();
      return '${dt.day.toString().padLeft(2, '0')}.${dt.month.toString().padLeft(2, '0')}.${dt.year}';
    } on Object {
      return isoString;
    }
  }
}

Color _statusColor(String status) {
  switch (status) {
    case 'draft':
      return const Color(0xFF2196F3);
    case 'reviewing':
      return const Color(0xFFFF9800);
    case 'finalized':
      return const Color(0xFF4CAF50);
    case 'generating':
      return const Color(0xFF9C27B0);
    case 'failed':
      return const Color(0xFFF44336);
    default:
      return const Color(0xFF757575);
  }
}

class _StatusBadge extends StatelessWidget {
  const _StatusBadge({required this.status});

  final String status;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final Color color = _statusColor(status);
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppConstants.spacingSm,
        vertical: AppConstants.spacingXs,
      ),
      decoration: BoxDecoration(
        color: color.withAlpha(30),
        borderRadius: BorderRadius.circular(AppConstants.radiusSm),
        border: Border.all(color: color.withAlpha(80)),
      ),
      child: Text(
        statusLabel(status),
        style: theme.textTheme.labelSmall?.copyWith(color: color),
      ),
    );
  }
}

final List<Map<String, String>> _draftTypes = const <Map<String, String>>[
  <String, String>{'value': 'aciklama_metni', 'label': 'Açıklama Metni'},
  <String, String>{'value': 'bilir_kisi_raporu', 'label': 'Bilirkişi Raporu'},
  <String, String>{'value': 'cevap_dilekcesi', 'label': 'Cevap Dilekçesi'},
  <String, String>{'value': 'dava_dilekcesi', 'label': 'Dava Dilekçesi'},
  <String, String>{'value': 'delil_listesi', 'label': 'Delil Listesi'},
  <String, String>{'value': 'durusma_tutanagi', 'label': 'Duruşma Tutanağı'},
  <String, String>{'value': 'genel_dilekce', 'label': 'Genel Dilekçe'},
  <String, String>{'value': 'hukuki_mutalaa', 'label': 'Hukuki Mütalaa'},
  <String, String>{'value': 'ihtarname', 'label': 'İhtarname'},
  <String, String>{'value': 'istinaf_dilekcesi', 'label': 'İstinaf Dilekçesi'},
  <String, String>{
    'value': 'kapanis_aciklamasi',
    'label': 'Kapanış Açıklaması',
  },
  <String, String>{'value': 'temyiz_dilekcesi', 'label': 'Temyiz Dilekçesi'},
];

void _showCreateDraftSheet(BuildContext context, WidgetRef ref, String caseId) {
  final GlobalKey<FormState> formKey = GlobalKey<FormState>();
  final TextEditingController titleController = TextEditingController();
  final TextEditingController supersedesController = TextEditingController();
  String selectedType = 'dava_dilekcesi';

  showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    useSafeArea: true,
    builder: (BuildContext sheetContext) {
      return Padding(
        padding: EdgeInsets.only(
          left: AppConstants.spacingMd,
          right: AppConstants.spacingMd,
          top: AppConstants.spacingMd,
          bottom:
              MediaQuery.of(sheetContext).viewInsets.bottom +
              AppConstants.spacingMd,
        ),
        child: Form(
          key: formKey,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              Text(
                'Yeni Taslak',
                style: Theme.of(sheetContext).textTheme.titleLarge,
              ),
              const SizedBox(height: AppConstants.spacingMd),
              TextFormField(
                controller: titleController,
                decoration: const InputDecoration(
                  labelText: 'Başlık',
                  hintText: 'Taslak başlığı',
                  border: OutlineInputBorder(),
                ),
                validator: (String? value) {
                  if (value == null || value.trim().isEmpty) {
                    return 'Başlık zorunludur';
                  }
                  return null;
                },
                textCapitalization: TextCapitalization.sentences,
              ),
              const SizedBox(height: AppConstants.spacingMd),
              DropdownButtonFormField<String>(
                value: selectedType,
                decoration: const InputDecoration(
                  labelText: 'Taslak Türü',
                  border: OutlineInputBorder(),
                ),
                items: _draftTypes.map((Map<String, String> t) {
                  return DropdownMenuItem<String>(
                    value: t['value'],
                    child: Text(t['label']!),
                  );
                }).toList(),
                onChanged: (String? value) {
                  if (value != null) {
                    selectedType = value;
                  }
                },
              ),
              const SizedBox(height: AppConstants.spacingMd),
              TextFormField(
                controller: supersedesController,
                decoration: const InputDecoration(
                  labelText: 'Yerine Geçtiği Taslak ID (isteğe bağlı)',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: AppConstants.spacingLg),
              Semantics(
                button: true,
                label: 'Taslağı oluştur',
                child: FilledButton(
                  onPressed: () async {
                    if (!formKey.currentState!.validate()) return;

                    try {
                      final DraftCreateResultItem result = await ref
                          .read(draftRepositoryProvider)
                          .createDraft(
                            caseId,
                            title: titleController.text.trim(),
                            draftType: selectedType,
                            supersedesDraftId:
                                supersedesController.text.trim().isEmpty
                                ? null
                                : supersedesController.text.trim(),
                          );

                      ref.invalidate(caseDraftsProvider(caseId));
                      Navigator.of(sheetContext).pop();

                      if (context.mounted) {
                        context.push('/cases/$caseId/drafts/${result.id}');
                      }
                    } on ApiException catch (e) {
                      ScaffoldMessenger.of(
                        sheetContext,
                      ).showSnackBar(SnackBar(content: Text(e.message)));
                    } on Object {
                      ScaffoldMessenger.of(sheetContext).showSnackBar(
                        const SnackBar(content: Text('Taslak oluşturulamadı.')),
                      );
                    }
                  },
                  child: const Text('Oluştur'),
                ),
              ),
            ],
          ),
        ),
      );
    },
  );
}
