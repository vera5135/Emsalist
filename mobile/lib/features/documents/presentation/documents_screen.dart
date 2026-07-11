import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/constants/app_constants.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/widgets/state_widgets.dart';
import '../application/document_providers.dart';
import '../domain/document_item.dart';

/// Documents screen for a case: list, upload (via a new-note composer for now),
/// per-document status, and navigation to the analysis detail. User-facing
/// text is non-technical; parser exceptions and queue internals are hidden.
class DocumentsScreen extends ConsumerWidget {
  const DocumentsScreen({required this.caseId, super.key});

  final String caseId;

  Future<void> _refresh(WidgetRef ref) async {
    ref.invalidate(documentsProvider(caseId));
    await ref.read(documentsProvider(caseId).future);
  }

  Future<void> _upload(BuildContext context, WidgetRef ref) async {
    final _NoteUpload? note = await showModalBottomSheet<_NoteUpload>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (BuildContext ctx) => const _UploadSheet(),
    );
    if (note == null) {
      return;
    }
    try {
      await ref.read(documentRepositoryProvider).upload(
            caseId,
            bytes: note.bytes,
            filename: note.filename,
            mimeType: 'text/plain',
          );
      ref.invalidate(documentsProvider(caseId));
    } on DuplicateDocumentException {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Bu belge bu dosyada zaten mevcut.')),
        );
      }
    } on ApiException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    } on Object {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Belge yüklenemedi.')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final AsyncValue<List<DocumentItem>> docs = ref.watch(documentsProvider(caseId));
    return Scaffold(
      appBar: AppBar(
        title: const Text('Belgeler'),
        actions: <Widget>[
          IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: 'Yenile',
            onPressed: () => ref.invalidate(documentsProvider(caseId)),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _upload(context, ref),
        icon: const Icon(Icons.upload_file),
        label: const Text('Belge Ekle'),
      ),
      body: docs.when(
        loading: () => const LoadingWidget(message: 'Belgeler yükleniyor'),
        error: (Object error, _) => AppErrorWidget(
          message: _messageFor(error),
          onRetry: () => ref.invalidate(documentsProvider(caseId)),
        ),
        data: (List<DocumentItem> items) {
          if (items.isEmpty) {
            return const EmptyWidget(
              title: 'Henüz belge yok',
              message: 'Belge ekleyerek dosyanızı zenginleştirin.',
              icon: Icons.folder_open_outlined,
            );
          }
          return RefreshIndicator(
            onRefresh: () => _refresh(ref),
            child: ListView.builder(
              padding: const EdgeInsets.only(bottom: 96),
              itemCount: items.length,
              itemBuilder: (BuildContext context, int index) {
                return _DocumentCard(caseId: caseId, document: items[index]);
              },
            ),
          );
        },
      ),
    );
  }

  static String _messageFor(Object error) {
    if (error is ApiException) {
      return error.message;
    }
    return 'Belgeler yüklenemedi.';
  }
}

String documentStatusLabel(DocumentItem d) {
  if (d.isProcessing) {
    return 'Belge inceleniyor';
  }
  if (d.isAwaitingConfirmation) {
    return 'Onayınızı bekleyen bilgiler var';
  }
  if (d.isAnalyzed) {
    return 'İnceleme tamamlandı';
  }
  if (d.isUnsupported) {
    return d.supportLevel == 'upload_only'
        ? 'Bu dosya türü henüz analiz edilemiyor'
        : 'Bu belge şu anda okunamadı';
  }
  if (d.isFailed) {
    return 'Bu belge şu anda okunamadı';
  }
  if (d.isQuarantined) {
    return 'Bu belge güvenlik incelemesinde';
  }
  return 'Belge yüklendi';
}

class _DocumentCard extends ConsumerWidget {
  const _DocumentCard({required this.caseId, required this.document});

  final String caseId;
  final DocumentItem document;

  Future<void> _retry(WidgetRef ref) async {
    await ref.read(documentRepositoryProvider).retry(caseId, document.id);
    ref.invalidate(documentsProvider(caseId));
  }

  Future<void> _delete(WidgetRef ref) async {
    await ref.read(documentRepositoryProvider).delete(caseId, document.id);
    ref.invalidate(documentsProvider(caseId));
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final ThemeData theme = Theme.of(context);
    final double kb = document.sizeBytes / 1024;
    return Card(
      child: ListTile(
        leading: Icon(_iconFor(document.extension)),
        title: Text(document.displayName),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            const SizedBox(height: AppConstants.spacingXs),
            Row(
              children: <Widget>[
                if (document.isProcessing)
                  const SizedBox(
                    height: 12,
                    width: 12,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  ),
                if (document.isProcessing)
                  const SizedBox(width: AppConstants.spacingSm),
                Flexible(
                  child: Text(
                    documentStatusLabel(document),
                    style: theme.textTheme.bodySmall,
                  ),
                ),
              ],
            ),
            Text(
              '${kb.toStringAsFixed(0)} KB'
              '${document.pageCount > 0 ? ' · ${document.pageCount} sayfa' : ''}',
              style: theme.textTheme.labelSmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ),
        trailing: PopupMenuButton<String>(
          onSelected: (String action) {
            switch (action) {
              case 'open':
                _openAnalysis(context);
              case 'retry':
                _retry(ref);
              case 'delete':
                _delete(ref);
            }
          },
          itemBuilder: (BuildContext ctx) => <PopupMenuEntry<String>>[
            const PopupMenuItem<String>(value: 'open', child: Text('İncele')),
            if (document.isFailed || document.isUnsupported)
              const PopupMenuItem<String>(value: 'retry', child: Text('Yeniden dene')),
            const PopupMenuItem<String>(value: 'delete', child: Text('Sil')),
          ],
        ),
        onTap: () => _openAnalysis(context),
      ),
    );
  }

  void _openAnalysis(BuildContext context) {
    Navigator.of(context).push<void>(
      MaterialPageRoute<void>(
        builder: (BuildContext ctx) =>
            DocumentAnalysisScreen(caseId: caseId, document: document),
      ),
    );
  }

  static IconData _iconFor(String extension) {
    switch (extension) {
      case '.pdf':
        return Icons.picture_as_pdf_outlined;
      case '.docx':
        return Icons.description_outlined;
      case '.jpg':
      case '.jpeg':
      case '.png':
        return Icons.image_outlined;
      default:
        return Icons.insert_drive_file_outlined;
    }
  }
}

class _NoteUpload {
  const _NoteUpload({required this.bytes, required this.filename});
  final List<int> bytes;
  final String filename;
}

class _UploadSheet extends StatefulWidget {
  const _UploadSheet();

  @override
  State<_UploadSheet> createState() => _UploadSheetState();
}

class _UploadSheetState extends State<_UploadSheet> {
  final TextEditingController _nameController = TextEditingController();
  final TextEditingController _bodyController = TextEditingController();

  @override
  void dispose() {
    _nameController.dispose();
    _bodyController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final EdgeInsets insets = MediaQuery.viewInsetsOf(context);
    return Padding(
      padding: EdgeInsets.only(
        left: AppConstants.spacingLg,
        right: AppConstants.spacingLg,
        top: AppConstants.spacingSm,
        bottom: AppConstants.spacingLg + insets.bottom,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Text('Belge Ekle', style: theme.textTheme.titleLarge),
          const SizedBox(height: AppConstants.spacingXs),
          Text(
            'Metin belgesi olarak ekleyin. Dosya seçici sonraki sürümde eklenecek.',
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(height: AppConstants.spacingMd),
          TextField(
            controller: _nameController,
            decoration: const InputDecoration(
              labelText: 'Belge adı',
              hintText: 'ör. Satış sözleşmesi',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: AppConstants.spacingMd),
          TextField(
            controller: _bodyController,
            minLines: 3,
            maxLines: 8,
            decoration: const InputDecoration(
              labelText: 'Belge metni',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: AppConstants.spacingLg),
          FilledButton(
            onPressed: () {
              final String body = _bodyController.text.trim();
              if (body.isEmpty) {
                return;
              }
              final String name = _nameController.text.trim();
              final String filename =
                  '${name.isEmpty ? 'belge' : name}.txt';
              Navigator.of(context).pop(
                _NoteUpload(bytes: body.codeUnits, filename: filename),
              );
            },
            child: const Text('Yükle'),
          ),
        ],
      ),
    );
  }
}

/// Document analysis detail: status, extraction suggestions with page
/// provenance, and confirm/reject actions.
class DocumentAnalysisScreen extends ConsumerWidget {
  const DocumentAnalysisScreen({
    required this.caseId,
    required this.document,
    super.key,
  });

  final String caseId;
  final DocumentItem document;

  String get _key => '$caseId::${document.id}';

  Future<void> _confirm(WidgetRef ref, String extractionId) async {
    await ref
        .read(documentRepositoryProvider)
        .confirmExtraction(caseId, document.id, extractionId);
    ref.invalidate(documentAnalysisProvider(_key));
  }

  Future<void> _reject(WidgetRef ref, String extractionId) async {
    await ref
        .read(documentRepositoryProvider)
        .rejectExtraction(caseId, document.id, extractionId);
    ref.invalidate(documentAnalysisProvider(_key));
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final ThemeData theme = Theme.of(context);
    final AsyncValue<DocumentAnalysis> analysis =
        ref.watch(documentAnalysisProvider(_key));
    return Scaffold(
      appBar: AppBar(title: Text(document.displayName)),
      body: analysis.when(
        loading: () => const LoadingWidget(message: 'Belge inceleniyor'),
        error: (Object error, _) => AppErrorWidget(
          message: error is ApiException ? error.message : 'Belge yüklenemedi.',
          onRetry: () => ref.invalidate(documentAnalysisProvider(_key)),
        ),
        data: (DocumentAnalysis data) {
          return RefreshIndicator(
            onRefresh: () async {
              ref.invalidate(documentAnalysisProvider(_key));
              await ref.read(documentAnalysisProvider(_key).future);
            },
            child: ListView(
              padding: const EdgeInsets.all(AppConstants.spacingMd),
              children: <Widget>[
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(documentStatusLabel(document)),
                  subtitle: Text(
                    data.extractedTextAvailable
                        ? '${data.pageCount} sayfa · metin çıkarıldı'
                        : 'Metin çıkarılamadı',
                  ),
                ),
                const Divider(),
                if (data.extractions.isEmpty)
                  const Padding(
                    padding: EdgeInsets.symmetric(vertical: AppConstants.spacingLg),
                    child: EmptyWidget(
                      title: 'Çıkarılan bilgi yok',
                      message: 'Bu belgeden onaylanacak bilgi bulunamadı.',
                      icon: Icons.search_off_outlined,
                    ),
                  )
                else ...<Widget>[
                  Text('Çıkarılan Bilgiler', style: theme.textTheme.titleMedium),
                  const SizedBox(height: AppConstants.spacingSm),
                  ...data.extractions.map(
                    (DocumentExtractionItem e) => Card(
                      child: ListTile(
                        title: Text(e.value),
                        subtitle: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: <Widget>[
                            Text(_fieldLabel(e.fieldKey)),
                            if (e.pageNumber != null)
                              Text(
                                'Kaynak: sayfa ${e.pageNumber}',
                                style: theme.textTheme.labelSmall?.copyWith(
                                  color: theme.colorScheme.onSurfaceVariant,
                                ),
                              ),
                          ],
                        ),
                        trailing: e.isPending
                            ? Row(
                                mainAxisSize: MainAxisSize.min,
                                children: <Widget>[
                                  IconButton(
                                    tooltip: 'Doğrula',
                                    icon: const Icon(Icons.check),
                                    onPressed: () => _confirm(ref, e.id),
                                  ),
                                  IconButton(
                                    tooltip: 'Reddet',
                                    icon: const Icon(Icons.close),
                                    onPressed: () => _reject(ref, e.id),
                                  ),
                                ],
                              )
                            : Text(
                                e.isConfirmed ? 'Doğrulandı' : 'Reddedildi',
                                style: theme.textTheme.labelSmall,
                              ),
                      ),
                    ),
                  ),
                ],
              ],
            ),
          );
        },
      ),
    );
  }

  static String _fieldLabel(String key) {
    switch (key) {
      case 'amount':
        return 'Tutar';
      case 'date':
        return 'Tarih';
      case 'vehicle_plate':
        return 'Plaka';
      case 'vehicle_vin':
        return 'Şasi/VIN';
      case 'case_number':
        return 'Esas numarası';
      case 'decision_number':
        return 'Karar numarası';
      default:
        return key;
    }
  }
}
