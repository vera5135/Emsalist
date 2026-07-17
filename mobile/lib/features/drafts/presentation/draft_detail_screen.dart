import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/constants/app_constants.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/widgets/state_widgets.dart';
import '../application/draft_job_poller.dart';
import '../application/draft_providers.dart';
import '../data/draft_repository.dart';
import '../domain/draft_item.dart';
import 'draft_edit_dialog.dart';
import 'draft_export_bar.dart';
import 'draft_review_sheet.dart';

class DraftDetailScreen extends ConsumerStatefulWidget {
  const DraftDetailScreen({
    required this.caseId,
    required this.draftId,
    super.key,
  });

  final String caseId;
  final String draftId;

  @override
  ConsumerState<DraftDetailScreen> createState() => _DraftDetailScreenState();
}

class _DraftDetailScreenState extends ConsumerState<DraftDetailScreen> {
  DraftReadinessItem? _readiness;
  DraftValidationItem? _validation;
  bool _readinessLoading = false;
  bool _validationLoading = false;
  bool _finalizing = false;
  bool _generating = false;
  bool _didShowSuccessDialog = false;

  DraftRepository get _repo => ref.read(draftRepositoryProvider);
  String get _caseId => widget.caseId;
  String get _draftId => widget.draftId;

  void _refreshDetail() {
    ref.invalidate(draftDetailProvider((caseId: _caseId, draftId: _draftId)));
  }

  Future<void> _checkReadiness() async {
    setState(() => _readinessLoading = true);
    try {
      final DraftReadinessItem result = await _repo.checkReadiness(
        _caseId,
        _draftId,
      );
      if (mounted) {
        setState(() => _readiness = result);
        _showReadinessResult(result);
      }
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(safeErrorMessage(e.code ?? ''))));
      }
    } on Object {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Hazırlık kontrolü yapılamadı.')),
        );
      }
    } finally {
      if (mounted) setState(() => _readinessLoading = false);
    }
  }

  void _showReadinessResult(DraftReadinessItem readiness) {
    showDialog<void>(
      context: context,
      builder: (BuildContext ctx) {
        final ThemeData theme = Theme.of(ctx);
        final bool ready = readiness.isReady;
        return AlertDialog(
          title: Row(
            children: <Widget>[
              Icon(
                ready
                    ? Icons.check_circle_outline
                    : Icons.warning_amber_outlined,
                color: ready
                    ? theme.colorScheme.primary
                    : theme.colorScheme.error,
              ),
              const SizedBox(width: AppConstants.spacingSm),
              Text(ready ? 'Taslak Hazır' : 'Taslak Hazır Değil'),
            ],
          ),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                _ReadinessStatusChip(status: readiness.status),
                if (readiness.blockedReasons.isNotEmpty) ...<Widget>[
                  const SizedBox(height: AppConstants.spacingMd),
                  Text('Engeller', style: theme.textTheme.titleSmall),
                  const SizedBox(height: AppConstants.spacingSm),
                  ...readiness.blockedReasons.map(
                    (String r) => Padding(
                      padding: const EdgeInsets.only(
                        bottom: AppConstants.spacingXs,
                      ),
                      child: Chip(
                        avatar: Icon(
                          Icons.block,
                          size: 16,
                          color: theme.colorScheme.error,
                        ),
                        label: Text(
                          r,
                          style: TextStyle(color: theme.colorScheme.error),
                        ),
                      ),
                    ),
                  ),
                ],
                if (readiness.warnings.isNotEmpty) ...<Widget>[
                  const SizedBox(height: AppConstants.spacingMd),
                  Text('Uyarılar', style: theme.textTheme.titleSmall),
                  const SizedBox(height: AppConstants.spacingSm),
                  ...readiness.warnings.map(
                    (String w) => Padding(
                      padding: const EdgeInsets.only(
                        bottom: AppConstants.spacingXs,
                      ),
                      child: Chip(
                        avatar: Icon(
                          Icons.warning_amber_outlined,
                          size: 16,
                          color: theme.colorScheme.tertiary,
                        ),
                        label: Text(w),
                      ),
                    ),
                  ),
                ],
                if (readiness.metrics.isNotEmpty) ...<Widget>[
                  const SizedBox(height: AppConstants.spacingMd),
                  Text('Ölçümler', style: theme.textTheme.titleSmall),
                  const SizedBox(height: AppConstants.spacingSm),
                  ...readiness.metrics.entries.map((
                    MapEntry<String, dynamic> e,
                  ) {
                    return Padding(
                      padding: const EdgeInsets.only(
                        bottom: AppConstants.spacingXs,
                      ),
                      child: Row(
                        children: <Widget>[
                          Expanded(
                            child: Text(
                              e.key,
                              style: theme.textTheme.bodySmall,
                            ),
                          ),
                          Text(
                            '${e.value}',
                            style: theme.textTheme.labelMedium,
                          ),
                        ],
                      ),
                    );
                  }),
                ],
              ],
            ),
          ),
          actions: <Widget>[
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(),
              child: const Text('Kapat'),
            ),
          ],
        );
      },
    );
  }

  Future<void> _validateDraft() async {
    setState(() => _validationLoading = true);
    try {
      final DraftValidationItem result = await _repo.validateDraft(
        _caseId,
        _draftId,
      );
      if (mounted) {
        setState(() => _validation = result);
        _showValidationResult(result);
      }
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(safeErrorMessage(e.code ?? ''))));
      }
    } on Object {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('Doğrulama yapılamadı.')));
      }
    } finally {
      if (mounted) setState(() => _validationLoading = false);
    }
  }

  void _showValidationResult(DraftValidationItem validation) {
    showDialog<void>(
      context: context,
      builder: (BuildContext ctx) {
        final ThemeData theme = Theme.of(ctx);
        return AlertDialog(
          title: Row(
            children: <Widget>[
              Icon(
                validation.valid
                    ? Icons.check_circle_outline
                    : Icons.error_outline,
                color: validation.valid
                    ? theme.colorScheme.primary
                    : theme.colorScheme.error,
              ),
              const SizedBox(width: AppConstants.spacingSm),
              Text(
                validation.valid ? 'Doğrulama Başarılı' : 'Doğrulama Başarısız',
              ),
            ],
          ),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                if (validation.blockingErrors.isNotEmpty) ...<Widget>[
                  Text(
                    'Engelleyici Hatalar',
                    style: theme.textTheme.titleSmall?.copyWith(
                      color: theme.colorScheme.error,
                    ),
                  ),
                  const SizedBox(height: AppConstants.spacingSm),
                  ...validation.blockingErrors.map(
                    (String err) => Padding(
                      padding: const EdgeInsets.only(
                        bottom: AppConstants.spacingXs,
                      ),
                      child: Chip(
                        avatar: Icon(
                          Icons.error,
                          size: 16,
                          color: theme.colorScheme.error,
                        ),
                        label: Text(err),
                      ),
                    ),
                  ),
                ],
                if (validation.warnings.isNotEmpty) ...<Widget>[
                  const SizedBox(height: AppConstants.spacingMd),
                  Text('Uyarılar', style: theme.textTheme.titleSmall),
                  const SizedBox(height: AppConstants.spacingSm),
                  ...validation.warnings.map(
                    (String w) => Padding(
                      padding: const EdgeInsets.only(
                        bottom: AppConstants.spacingXs,
                      ),
                      child: Chip(
                        avatar: Icon(
                          Icons.warning_amber_outlined,
                          size: 16,
                          color: theme.colorScheme.tertiary,
                        ),
                        label: Text(w),
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ),
          actions: <Widget>[
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(),
              child: const Text('Kapat'),
            ),
          ],
        );
      },
    );
  }

  Future<void> _enqueueGeneration(DraftDetailItem draft) async {
    final DraftGenerationJobNotifier notifier = ref.read(
      draftGenerationJobProvider((caseId: _caseId, draftId: _draftId)).notifier,
    );

    setState(() => _generating = true);
    try {
      await notifier.enqueue(
        caseId: _caseId,
        draftId: _draftId,
        draftVersion: draft.version,
      );
    } finally {
      if (mounted) setState(() => _generating = false);
    }
  }

  Future<void> _finalizeDraft(DraftDetailItem draft) async {
    final bool confirmed =
        await showDialog<bool>(
          context: context,
          builder: (BuildContext ctx) {
            return AlertDialog(
              title: const Text('Taslağı Tamamla'),
              content: const Text(
                'Bu taslağı tamamlamak istediğinize emin misiniz? '
                'Tamamlandıktan sonra düzenleme yapılamaz.',
              ),
              actions: <Widget>[
                TextButton(
                  onPressed: () => Navigator.of(ctx).pop(false),
                  child: const Text('İptal'),
                ),
                FilledButton(
                  onPressed: () => Navigator.of(ctx).pop(true),
                  child: const Text('Tamamla'),
                ),
              ],
            );
          },
        ) ??
        false;

    if (!confirmed) return;

    setState(() => _finalizing = true);
    try {
      await _repo.finalizeDraft(_caseId, _draftId, version: draft.version);
      _refreshDetail();
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('Taslak tamamlandı.')));
      }
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(safeErrorMessage(e.code ?? ''))));
      }
    } on Object {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('Taslak tamamlanamadı.')));
      }
    } finally {
      if (mounted) setState(() => _finalizing = false);
    }
  }

  Future<void> _editParagraph(
    DraftDetailItem draft,
    DraftParagraphItem paragraph,
  ) async {
    await showEditParagraphDialog(
      context,
      paragraph: paragraph,
      onSave: (String text) async {
        await _repo.editParagraph(
          _caseId,
          _draftId,
          paragraph.id,
          draftVersion: draft.version,
          paragraphVersion: paragraph.version,
          text: text,
        );
        _refreshDetail();
      },
    );
  }

  Future<void> _acceptParagraph(
    DraftDetailItem draft,
    DraftParagraphItem paragraph,
  ) async {
    if (paragraph.currentRevisionId == null) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Kabul edilecek sürüm bulunamadı.')),
        );
      }
      return;
    }
    try {
      await _repo.acceptParagraph(
        _caseId,
        _draftId,
        paragraph.id,
        draftVersion: draft.version,
        paragraphVersion: paragraph.version,
        revisionId: paragraph.currentRevisionId!,
      );
      _refreshDetail();
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('Paragraf kabul edildi.')));
      }
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(safeErrorMessage(e.code ?? ''))));
      }
    } on Object {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Paragraf kabul edilemedi.')),
        );
      }
    }
  }

  void _requestChanges(DraftDetailItem draft, DraftParagraphItem paragraph) {
    if (paragraph.currentRevisionId == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Değişiklik istenecek sürüm bulunamadı.')),
      );
      return;
    }

    showRequestChangesSheet(
      context,
      onConfirm: (String reasonCode) async {
        try {
          await _repo.requestChanges(
            _caseId,
            _draftId,
            paragraph.id,
            draftVersion: draft.version,
            paragraphVersion: paragraph.version,
            revisionId: paragraph.currentRevisionId!,
            reasonCode: reasonCode,
          );
          _refreshDetail();
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(content: Text('Değişiklik talebi gönderildi.')),
            );
          }
        } on ApiException catch (e) {
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(content: Text(safeErrorMessage(e.code ?? ''))),
            );
          }
        } on Object {
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(content: Text('Değişiklik talebi gönderilemedi.')),
            );
          }
        }
      },
    );
  }

  Future<void> _showRevisions(DraftParagraphItem paragraph) async {
    List<DraftRevisionItem> revisions;
    try {
      revisions = await _repo.listRevisions(_caseId, _draftId, paragraph.id);
    } on Object {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Sürüm geçmişi yüklenemedi.')),
        );
      }
      return;
    }

    if (!mounted) return;

    showRevisionHistorySheet(
      context,
      revisions: revisions,
      currentParagraph: paragraph,
      onRestore: (String revisionId) async {
        try {
          await _repo.restoreRevision(
            _caseId,
            _draftId,
            paragraph.id,
            revisionId: revisionId,
            draftVersion: paragraph.version,
            paragraphVersion: paragraph.version,
          );
          _refreshDetail();
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(content: Text('Sürüm geri yüklendi.')),
            );
          }
        } on ApiException catch (e) {
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(content: Text(safeErrorMessage(e.code ?? ''))),
            );
          }
        } on Object {
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(content: Text('Sürüm geri yüklenemedi.')),
            );
          }
        }
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final AsyncValue<DraftDetailItem> detail = ref.watch(
      draftDetailProvider((caseId: _caseId, draftId: _draftId)),
    );

    final DraftGenerationJobState jobState = ref.watch(
      draftGenerationJobProvider((caseId: _caseId, draftId: _draftId)),
    );

    ref.listen(
      draftGenerationJobProvider((caseId: _caseId, draftId: _draftId)),
      (DraftGenerationJobState? previous, DraftGenerationJobState next) {
        if (next.status == 'succeeded' && !_didShowSuccessDialog && mounted) {
          _didShowSuccessDialog = true;
          showDialog<void>(
            context: context,
            builder: (BuildContext ctx) {
              return AlertDialog(
                title: const Text('Taslak Oluşturuldu'),
                content: const Text('Taslak başarıyla oluşturuldu.'),
                actions: <Widget>[
                  FilledButton(
                    onPressed: () {
                      Navigator.of(ctx).pop();
                      _refreshDetail();
                    },
                    child: const Text('Tamam'),
                  ),
                ],
              );
            },
          );
        }
        if (next.status.isEmpty && next.enqueueError == null) {
          _didShowSuccessDialog = false;
        }
      },
    );

    return Scaffold(
      appBar: AppBar(title: const Text('Taslak Detayı')),
      body: detail.when(
        loading: () => const LoadingWidget(message: 'Taslak yükleniyor'),
        error: (Object error, _) => AppErrorWidget(
          message: error is ApiException
              ? error.message
              : 'Taslak yüklenemedi.',
          onRetry: () => _refreshDetail(),
        ),
        data: (DraftDetailItem draft) {
          final bool editable = draft.isEditable;
          final bool isFinalized = draft.status == 'finalized';
          final bool showGenerate = editable && draft.paragraphs.isEmpty;
          final bool allAccepted =
              draft.paragraphs.isNotEmpty &&
              draft.paragraphs.every(
                (DraftParagraphItem p) => p.verificationStatus == 'accepted',
              );

          return RefreshIndicator(
            onRefresh: () async {
              _refreshDetail();
              await ref.read(
                draftDetailProvider((
                  caseId: _caseId,
                  draftId: _draftId,
                )).future,
              );
            },
            child: CustomScrollView(
              slivers: <Widget>[
                SliverToBoxAdapter(
                  child: _DraftHeader(
                    draft: draft,
                    editable: editable,
                    isFinalized: isFinalized,
                  ),
                ),
                if (isFinalized)
                  SliverToBoxAdapter(child: _FinalizedBanner(theme: theme)),
                if (jobState.isPolling ||
                    jobState.status == 'succeeded' ||
                    jobState.status == 'failed')
                  SliverToBoxAdapter(
                    child: _GenerationProgress(
                      jobState: jobState,
                      theme: theme,
                      draft: draft,
                      onRefreshDetail: _refreshDetail,
                    ),
                  ),
                if (jobState.enqueueError != null)
                  SliverToBoxAdapter(
                    child: _GenerationError(
                      error: jobState.enqueueError!,
                      draft: draft,
                      onRetry: () => _enqueueGeneration(draft),
                    ),
                  ),
                SliverToBoxAdapter(
                  child: _ActionBar(
                    editable: editable,
                    isFinalized: isFinalized,
                    showGenerate: showGenerate,
                    allAccepted: allAccepted,
                    finalizing: _finalizing,
                    generating: _generating,
                    generatingActive:
                        jobState.isPolling || jobState.status == 'queued',
                    readinessLoading: _readinessLoading,
                    validationLoading: _validationLoading,
                    onReadiness: _checkReadiness,
                    onValidate: _validateDraft,
                    onGenerate: () => _enqueueGeneration(draft),
                    onFinalize: () => _finalizeDraft(draft),
                  ),
                ),
                if (isFinalized)
                  SliverToBoxAdapter(
                    child: DraftExportBar(caseId: _caseId, draftId: _draftId),
                  ),
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(
                      horizontal: AppConstants.spacingMd,
                      vertical: AppConstants.spacingSm,
                    ),
                    child: Text(
                      'Paragraflar (${draft.paragraphs.length})',
                      style: theme.textTheme.titleMedium,
                    ),
                  ),
                ),
                if (draft.paragraphs.isEmpty)
                  SliverToBoxAdapter(
                    child: const Padding(
                      padding: EdgeInsets.all(AppConstants.spacingMd),
                      child: EmptyWidget(
                        title: 'Henüz paragraf yok',
                        message:
                            'Yapay zeka ile paragraf oluşturun veya manuel ekleyin.',
                        icon: Icons.text_fields,
                      ),
                    ),
                  )
                else
                  SliverList(
                    delegate: SliverChildBuilderDelegate((
                      BuildContext context,
                      int index,
                    ) {
                      final DraftParagraphItem paragraph =
                          draft.paragraphs[index];
                      final List<DraftIssueLinkItem> paraIssues = draft
                          .issueLinks
                          .where(
                            (DraftIssueLinkItem il) =>
                                il.draftParagraphId == paragraph.id,
                          )
                          .toList();
                      final List<DraftSourceLinkItem> paraSources = draft
                          .sourceLinks
                          .where(
                            (DraftSourceLinkItem sl) =>
                                sl.draftParagraphId == paragraph.id,
                          )
                          .toList();
                      return _ParagraphCard(
                        paragraph: paragraph,
                        draft: draft,
                        editable: editable,
                        issueLinks: paraIssues,
                        sourceLinks: paraSources,
                        onEdit: () => _editParagraph(draft, paragraph),
                        onAccept: () => _acceptParagraph(draft, paragraph),
                        onRequestChanges: () =>
                            _requestChanges(draft, paragraph),
                        onShowRevisions: () => _showRevisions(paragraph),
                      );
                    }, childCount: draft.paragraphs.length),
                  ),
                const SliverToBoxAdapter(
                  child: SizedBox(height: AppConstants.spacingXl),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}

class _DraftHeader extends StatelessWidget {
  const _DraftHeader({
    required this.draft,
    required this.editable,
    required this.isFinalized,
  });

  final DraftDetailItem draft;
  final bool editable;
  final bool isFinalized;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.all(AppConstants.spacingMd),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Expanded(
                child: Text(draft.title, style: theme.textTheme.headlineSmall),
              ),
              _StatusBadge(status: draft.status),
            ],
          ),
          const SizedBox(height: AppConstants.spacingSm),
          Row(
            children: <Widget>[
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: AppConstants.spacingSm,
                  vertical: AppConstants.spacingXs,
                ),
                decoration: BoxDecoration(
                  color: theme.colorScheme.surfaceContainerHighest,
                  borderRadius: BorderRadius.circular(AppConstants.radiusSm),
                ),
                child: Text(draft.label, style: theme.textTheme.labelMedium),
              ),
              const SizedBox(width: AppConstants.spacingSm),
              Text(
                'Sürüm ${draft.version}',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            ],
          ),
          if (draft.finalizedAt != null) ...[
            const SizedBox(height: AppConstants.spacingXs),
            Text(
              'Tamamlanma: ${draft.finalizedAt}',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.primary,
              ),
            ),
          ],
          if (draft.supersedesDraftId != null) ...[
            const SizedBox(height: AppConstants.spacingXs),
            Text(
              'Yerine geçtiği: ${draft.supersedesDraftId}',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _FinalizedBanner extends StatelessWidget {
  const _FinalizedBanner({required this.theme});

  final ThemeData theme;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.symmetric(
        horizontal: AppConstants.spacingMd,
        vertical: AppConstants.spacingSm,
      ),
      padding: const EdgeInsets.all(AppConstants.spacingMd),
      decoration: BoxDecoration(
        color: theme.colorScheme.primaryContainer.withAlpha(80),
        borderRadius: BorderRadius.circular(AppConstants.radiusMd),
        border: Border.all(color: theme.colorScheme.primary.withAlpha(60)),
      ),
      child: Row(
        children: <Widget>[
          Icon(Icons.info_outline, color: theme.colorScheme.primary, size: 20),
          const SizedBox(width: AppConstants.spacingSm),
          Expanded(
            child: Text(
              'Bu taslak tamamlanmıştır — salt okunur',
              style: theme.textTheme.bodyMedium?.copyWith(
                color: theme.colorScheme.primary,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ActionBar extends StatelessWidget {
  const _ActionBar({
    required this.editable,
    required this.isFinalized,
    required this.showGenerate,
    required this.allAccepted,
    required this.finalizing,
    required this.generating,
    required this.generatingActive,
    required this.readinessLoading,
    required this.validationLoading,
    required this.onReadiness,
    required this.onValidate,
    required this.onGenerate,
    required this.onFinalize,
  });

  final bool editable;
  final bool isFinalized;
  final bool showGenerate;
  final bool allAccepted;
  final bool finalizing;
  final bool generating;
  final bool generatingActive;
  final bool readinessLoading;
  final bool validationLoading;
  final VoidCallback onReadiness;
  final VoidCallback onValidate;
  final VoidCallback onGenerate;
  final VoidCallback onFinalize;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(
        horizontal: AppConstants.spacingMd,
        vertical: AppConstants.spacingSm,
      ),
      child: Wrap(
        spacing: AppConstants.spacingSm,
        runSpacing: AppConstants.spacingSm,
        children: <Widget>[
          Semantics(
            button: true,
            label: 'Hazırlık kontrolü',
            child: ActionChip(
              avatar: readinessLoading
                  ? const SizedBox.square(
                      dimension: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.checklist, size: 18),
              label: Text(readinessLoading ? 'Kontrol...' : 'Hazırlık'),
              onPressed: readinessLoading ? null : onReadiness,
            ),
          ),
          Semantics(
            button: true,
            label: 'Doğrula',
            child: ActionChip(
              avatar: validationLoading
                  ? const SizedBox.square(
                      dimension: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.verified_outlined, size: 18),
              label: Text(validationLoading ? 'Doğrulanıyor...' : 'Doğrula'),
              onPressed: validationLoading ? null : onValidate,
            ),
          ),
          if (showGenerate)
            Semantics(
              button: true,
              label: 'Yapay zeka ile oluştur',
              child: ActionChip(
                avatar: generating || generatingActive
                    ? const SizedBox.square(
                        dimension: 16,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.auto_awesome, size: 18),
                label: Text(generatingActive ? 'Oluşturuluyor...' : 'Oluştur'),
                onPressed: (generating || generatingActive) ? null : onGenerate,
              ),
            ),
          if (editable && !isFinalized)
            Semantics(
              button: true,
              label: 'Tamamla',
              child: ActionChip(
                avatar: finalizing
                    ? const SizedBox.square(
                        dimension: 16,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.check_circle_outline, size: 18),
                label: Text(finalizing ? 'Tamamlanıyor...' : 'Tamamla'),
                onPressed: finalizing ? null : onFinalize,
              ),
            ),
        ],
      ),
    );
  }
}

class _GenerationProgress extends StatelessWidget {
  const _GenerationProgress({
    required this.jobState,
    required this.theme,
    required this.draft,
    required this.onRefreshDetail,
  });

  final DraftGenerationJobState jobState;
  final ThemeData theme;
  final DraftDetailItem draft;
  final VoidCallback onRefreshDetail;

  @override
  Widget build(BuildContext context) {
    final String stageLabel = stageLabelText(jobState.stage);

    return Container(
      margin: const EdgeInsets.all(AppConstants.spacingMd),
      padding: const EdgeInsets.all(AppConstants.spacingMd),
      decoration: BoxDecoration(
        color: theme.colorScheme.tertiaryContainer.withAlpha(60),
        borderRadius: BorderRadius.circular(AppConstants.radiusMd),
        border: Border.all(color: theme.colorScheme.tertiary.withAlpha(60)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Icon(
                Icons.auto_awesome,
                size: 20,
                color: theme.colorScheme.tertiary,
              ),
              const SizedBox(width: AppConstants.spacingSm),
              Expanded(
                child: Text(
                  jobState.isPolling
                      ? stageLabel
                      : jobState.status == 'succeeded'
                      ? 'Oluşturma tamamlandı'
                      : 'Oluşturma başarısız',
                  style: theme.textTheme.titleSmall,
                ),
              ),
            ],
          ),
          const SizedBox(height: AppConstants.spacingSm),
          LinearProgressIndicator(
            value: jobState.progressPercent / 100,
            backgroundColor: theme.colorScheme.tertiaryContainer,
            color: jobState.status == 'failed'
                ? theme.colorScheme.error
                : theme.colorScheme.tertiary,
          ),
          const SizedBox(height: AppConstants.spacingXs),
          Text(
            '%${jobState.progressPercent}',
            style: theme.textTheme.bodySmall,
          ),
          if (jobState.status == 'failed' &&
              jobState.safeErrorCode != null &&
              jobState.safeErrorCode!.isNotEmpty) ...[
            const SizedBox(height: AppConstants.spacingSm),
            Text(
              safeErrorMessage(jobState.safeErrorCode!),
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.error,
              ),
            ),
          ],
          if (jobState.status == 'succeeded')
            Padding(
              padding: const EdgeInsets.only(top: AppConstants.spacingSm),
              child: FilledButton(
                onPressed: onRefreshDetail,
                child: const Text('Taslağı Görüntüle'),
              ),
            ),
        ],
      ),
    );
  }
}

class _GenerationError extends StatelessWidget {
  const _GenerationError({
    required this.error,
    required this.draft,
    required this.onRetry,
  });

  final String error;
  final DraftDetailItem draft;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Container(
      margin: const EdgeInsets.all(AppConstants.spacingMd),
      padding: const EdgeInsets.all(AppConstants.spacingMd),
      decoration: BoxDecoration(
        color: theme.colorScheme.errorContainer.withAlpha(60),
        borderRadius: BorderRadius.circular(AppConstants.radiusMd),
        border: Border.all(color: theme.colorScheme.error.withAlpha(60)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Icon(Icons.error_outline, color: theme.colorScheme.error),
              const SizedBox(width: AppConstants.spacingSm),
              Expanded(
                child: Text(
                  error,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: theme.colorScheme.error,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: AppConstants.spacingSm),
          FilledButton(onPressed: onRetry, child: const Text('Tekrar Dene')),
        ],
      ),
    );
  }
}

class _ParagraphCard extends StatelessWidget {
  const _ParagraphCard({
    required this.paragraph,
    required this.draft,
    required this.editable,
    required this.issueLinks,
    required this.sourceLinks,
    required this.onEdit,
    required this.onAccept,
    required this.onRequestChanges,
    required this.onShowRevisions,
  });

  final DraftParagraphItem paragraph;
  final DraftDetailItem draft;
  final bool editable;
  final List<DraftIssueLinkItem> issueLinks;
  final List<DraftSourceLinkItem> sourceLinks;
  final VoidCallback onEdit;
  final VoidCallback onAccept;
  final VoidCallback onRequestChanges;
  final VoidCallback onShowRevisions;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Card(
      margin: const EdgeInsets.symmetric(
        horizontal: AppConstants.spacingMd,
        vertical: AppConstants.spacingXs,
      ),
      child: ExpansionTile(
        title: Row(
          children: <Widget>[
            Text(
              '${paragraph.order + 1}. ${paragraph.label}',
              style: theme.textTheme.titleSmall,
            ),
            const SizedBox(width: AppConstants.spacingSm),
            _VerificationChip(status: paragraph.verificationStatus),
          ],
        ),
        subtitle: Row(
          children: <Widget>[
            if (paragraph.isAiGenerated) ...[
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: AppConstants.spacingSm,
                  vertical: 2,
                ),
                decoration: BoxDecoration(
                  color: theme.colorScheme.tertiaryContainer,
                  borderRadius: BorderRadius.circular(AppConstants.radiusSm),
                ),
                child: Text(
                  paragraph.modelName != null
                      ? 'Yapay Zeka · ${paragraph.modelName}'
                      : 'Yapay Zeka',
                  style: theme.textTheme.labelSmall?.copyWith(
                    color: theme.colorScheme.tertiary,
                  ),
                ),
              ),
              const SizedBox(width: AppConstants.spacingSm),
            ],
            if (issueLinks.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(right: AppConstants.spacingSm),
                child: _LinkBadge(
                  count: issueLinks.length,
                  label: 'Hukuki konu',
                  color: theme.colorScheme.primary,
                ),
              ),
            if (sourceLinks.isNotEmpty)
              _LinkBadge(
                count: sourceLinks.length,
                label: 'Kayıt',
                color: theme.colorScheme.tertiary,
              ),
          ],
        ),
        children: <Widget>[
          const Divider(height: 1),
          Padding(
            padding: const EdgeInsets.all(AppConstants.spacingMd),
            child: SelectableText(
              paragraph.text,
              style: theme.textTheme.bodyMedium,
            ),
          ),
          if (paragraph.effectiveTrust != null)
            Padding(
              padding: const EdgeInsets.symmetric(
                horizontal: AppConstants.spacingMd,
              ),
              child: Row(
                children: <Widget>[
                  Icon(
                    Icons.verified_outlined,
                    size: 14,
                    color: theme.colorScheme.outline,
                  ),
                  const SizedBox(width: AppConstants.spacingXs),
                  Text(
                    'Doğruluk puanı: ${(paragraph.effectiveTrust! * 100).toStringAsFixed(0)}%',
                    style: theme.textTheme.bodySmall,
                  ),
                ],
              ),
            ),
          if (issueLinks.isNotEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(
                horizontal: AppConstants.spacingMd,
                vertical: AppConstants.spacingXs,
              ),
              child: Wrap(
                spacing: AppConstants.spacingXs,
                runSpacing: AppConstants.spacingXs,
                children: issueLinks.map((DraftIssueLinkItem il) {
                  return Chip(
                    avatar: Icon(
                      Icons.account_tree_outlined,
                      size: 14,
                      color: theme.colorScheme.primary,
                    ),
                    label: Text(
                      il.legalIssueId,
                      style: theme.textTheme.labelSmall,
                    ),
                    materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                    visualDensity: VisualDensity.compact,
                  );
                }).toList(),
              ),
            ),
          if (sourceLinks.isNotEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(
                horizontal: AppConstants.spacingMd,
                vertical: AppConstants.spacingXs,
              ),
              child: Wrap(
                spacing: AppConstants.spacingXs,
                runSpacing: AppConstants.spacingXs,
                children: sourceLinks.map((DraftSourceLinkItem sl) {
                  final String trustLabel = sl.effectiveTrust != null
                      ? ' (%${(sl.effectiveTrust! * 100).toStringAsFixed(0)})'
                      : '';
                  return Chip(
                    avatar: Icon(
                      sl.isVerified ? Icons.verified : Icons.link,
                      size: 14,
                      color: sl.isVerified
                          ? theme.colorScheme.primary
                          : theme.colorScheme.outline,
                    ),
                    label: Text(
                      '${sl.sourceRecordId}$trustLabel',
                      style: theme.textTheme.labelSmall,
                    ),
                    materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                    visualDensity: VisualDensity.compact,
                  );
                }).toList(),
              ),
            ),
          if (editable)
            Padding(
              padding: const EdgeInsets.fromLTRB(
                AppConstants.spacingSm,
                0,
                AppConstants.spacingSm,
                AppConstants.spacingSm,
              ),
              child: Wrap(
                spacing: AppConstants.spacingXs,
                runSpacing: AppConstants.spacingXs,
                children: <Widget>[
                  Semantics(
                    button: true,
                    label: 'Paragrafı düzenle',
                    child: ActionChip(
                      avatar: const Icon(Icons.edit, size: 18),
                      label: const Text('Düzenle'),
                      onPressed: onEdit,
                    ),
                  ),
                  Semantics(
                    button: true,
                    label: 'Paragrafı kabul et',
                    child: ActionChip(
                      avatar: Icon(
                        Icons.check_circle_outline,
                        size: 18,
                        color: theme.colorScheme.primary,
                      ),
                      label: const Text('Kabul Et'),
                      onPressed: onAccept,
                    ),
                  ),
                  Semantics(
                    button: true,
                    label: 'Değişiklik iste',
                    child: ActionChip(
                      avatar: Icon(
                        Icons.rate_review_outlined,
                        size: 18,
                        color: theme.colorScheme.tertiary,
                      ),
                      label: const Text('Değişiklik İste'),
                      onPressed: onRequestChanges,
                    ),
                  ),
                  Semantics(
                    button: true,
                    label: 'Geçmiş sürümler',
                    child: ActionChip(
                      avatar: const Icon(Icons.history, size: 18),
                      label: const Text('Geçmiş'),
                      onPressed: onShowRevisions,
                    ),
                  ),
                ],
              ),
            ),
          const SizedBox(height: AppConstants.spacingSm),
        ],
      ),
    );
  }
}

class _VerificationChip extends StatelessWidget {
  const _VerificationChip({required this.status});

  final String status;

  @override
  Widget build(BuildContext context) {
    final Color color;
    final String label;
    switch (status) {
      case 'accepted':
        color = const Color(0xFF4CAF50);
        label = 'Kabul edildi';
        break;
      case 'needs_review':
        color = const Color(0xFFF44336);
        label = 'İnceleme gerekli';
        break;
      default:
        color = const Color(0xFF757575);
        label = 'İnceleniyor';
    }
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppConstants.spacingSm,
        vertical: 2,
      ),
      decoration: BoxDecoration(
        color: color.withAlpha(25),
        borderRadius: BorderRadius.circular(AppConstants.radiusSm),
        border: Border.all(color: color.withAlpha(80)),
      ),
      child: Text(
        label,
        style: Theme.of(context).textTheme.labelSmall?.copyWith(color: color),
      ),
    );
  }
}

class _ReadinessStatusChip extends StatelessWidget {
  const _ReadinessStatusChip({required this.status});

  final String status;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final bool ready = status == 'ready';
    return Chip(
      avatar: Icon(
        ready ? Icons.check_circle : Icons.warning_amber,
        size: 16,
        color: ready ? theme.colorScheme.primary : theme.colorScheme.error,
      ),
      label: Text(
        status == 'ready'
            ? 'Hazır'
            : status == 'ready_with_warnings'
            ? 'Uyarılarla Hazır'
            : 'Engelli',
      ),
    );
  }
}

class _LinkBadge extends StatelessWidget {
  const _LinkBadge({
    required this.count,
    required this.label,
    required this.color,
  });

  final int count;
  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppConstants.spacingSm,
        vertical: 2,
      ),
      decoration: BoxDecoration(
        color: color.withAlpha(25),
        borderRadius: BorderRadius.circular(AppConstants.radiusSm),
        border: Border.all(color: color.withAlpha(80)),
      ),
      child: Text(
        '$count $label',
        style: Theme.of(context).textTheme.labelSmall?.copyWith(color: color),
      ),
    );
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
    case 'superseded':
      return const Color(0xFF757575);
    default:
      return const Color(0xFF757575);
  }
}

class _StatusBadge extends StatelessWidget {
  const _StatusBadge({required this.status});

  final String status;

  @override
  Widget build(BuildContext context) {
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
        style: Theme.of(context).textTheme.labelSmall?.copyWith(color: color),
      ),
    );
  }
}
