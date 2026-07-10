import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../app/app_router.dart';
import '../../../core/constants/app_constants.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/widgets/state_widgets.dart';
import '../application/case_providers.dart';
import '../domain/case_item.dart';

/// Case list screen: active + archived cases, new-case flow, active selection.
class CasesScreen extends ConsumerWidget {
  const CasesScreen({super.key});

  Future<void> _createCase(BuildContext context, WidgetRef ref) async {
    final CaseItem? created = await showModalBottomSheet<CaseItem>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (BuildContext ctx) => const NewCaseSheet(),
    );
    if (created != null) {
      ref.invalidate(activeCasesProvider);
      ref.read(activeCaseIdProvider.notifier).select(created.id);
      if (context.mounted) {
        context.goNamed(
          AppRoutes.caseChat,
          pathParameters: <String, String>{'caseId': created.id},
        );
      }
    }
  }

  Future<void> _archive(WidgetRef ref, String caseId) async {
    await ref.read(caseRepositoryProvider).archiveCase(caseId);
    ref.invalidate(activeCasesProvider);
    ref.invalidate(archivedCasesProvider);
  }

  Future<void> _restore(WidgetRef ref, String caseId) async {
    await ref.read(caseRepositoryProvider).restoreCase(caseId);
    ref.invalidate(activeCasesProvider);
    ref.invalidate(archivedCasesProvider);
  }

  void _openCase(BuildContext context, WidgetRef ref, String caseId) {
    ref.read(activeCaseIdProvider.notifier).select(caseId);
    context.goNamed(
      AppRoutes.caseChat,
      pathParameters: <String, String>{'caseId': caseId},
    );
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final AsyncValue<List<CaseItem>> active = ref.watch(activeCasesProvider);
    final AsyncValue<List<CaseItem>> archived = ref.watch(
      archivedCasesProvider,
    );

    return Scaffold(
      appBar: AppBar(
        title: const Text('Dosyalar'),
        actions: <Widget>[
          IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: 'Yenile',
            onPressed: () {
              ref.invalidate(activeCasesProvider);
              ref.invalidate(archivedCasesProvider);
            },
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _createCase(context, ref),
        icon: const Icon(Icons.add),
        label: const Text('Yeni Dosya'),
      ),
      body: active.when(
        loading: () => const LoadingWidget(message: 'Dosyalar yükleniyor'),
        error: (Object error, _) => AppErrorWidget(
          message: _messageFor(error),
          onRetry: () => ref.invalidate(activeCasesProvider),
        ),
        data: (List<CaseItem> cases) {
          final List<CaseItem> archivedList = archived.maybeWhen(
            data: (List<CaseItem> a) => a,
            orElse: () => const <CaseItem>[],
          );
          if (cases.isEmpty && archivedList.isEmpty) {
            return const EmptyWidget(
              title: 'Henüz dosya yok',
              message: 'Yeni bir dosya oluşturarak başlayın.',
              icon: Icons.folder_outlined,
            );
          }
          return RefreshIndicator(
            onRefresh: () async {
              ref.invalidate(activeCasesProvider);
              ref.invalidate(archivedCasesProvider);
              await ref.read(activeCasesProvider.future);
            },
            child: ListView(
              padding: const EdgeInsets.only(bottom: 96),
              children: <Widget>[
                if (cases.isNotEmpty)
                  const _SectionHeader(title: 'Aktif Dosyalar'),
                ...cases.map(
                  (CaseItem c) => _CaseTile(
                    item: c,
                    onTap: () => _openCase(context, ref, c.id),
                    trailing: IconButton(
                      icon: const Icon(Icons.archive_outlined),
                      tooltip: 'Arşivle',
                      onPressed: () => _archive(ref, c.id),
                    ),
                  ),
                ),
                if (archivedList.isNotEmpty) ...<Widget>[
                  const _SectionHeader(title: 'Arşiv'),
                  ...archivedList.map(
                    (CaseItem c) => _CaseTile(
                      item: c,
                      onTap: () => _openCase(context, ref, c.id),
                      trailing: IconButton(
                        icon: const Icon(Icons.unarchive_outlined),
                        tooltip: 'Geri yükle',
                        onPressed: () => _restore(ref, c.id),
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

  static String _messageFor(Object error) {
    if (error is ApiException) {
      return error.message;
    }
    return 'Dosyalar yüklenemedi.';
  }
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader({required this.title});

  final String title;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        AppConstants.spacingMd,
        AppConstants.spacingMd,
        AppConstants.spacingMd,
        AppConstants.spacingSm,
      ),
      child: Text(
        title,
        style: theme.textTheme.labelLarge?.copyWith(
          color: theme.colorScheme.onSurfaceVariant,
        ),
      ),
    );
  }
}

class _CaseTile extends StatelessWidget {
  const _CaseTile({required this.item, required this.onTap, this.trailing});

  final CaseItem item;
  final VoidCallback onTap;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: const Icon(Icons.folder_outlined),
      title: Text(item.displayTitle),
      subtitle: item.legalTopic.trim().isEmpty ? null : Text(item.legalTopic),
      trailing: trailing,
      onTap: onTap,
    );
  }
}

/// Bottom sheet to create a new case. Pops the created [CaseItem] on success.
class NewCaseSheet extends ConsumerStatefulWidget {
  const NewCaseSheet({super.key});

  @override
  ConsumerState<NewCaseSheet> createState() => _NewCaseSheetState();
}

class _NewCaseSheetState extends ConsumerState<NewCaseSheet> {
  final TextEditingController _titleController = TextEditingController();
  final TextEditingController _topicController = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _titleController.dispose();
    _topicController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_busy) {
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final CaseItem created = await ref
          .read(caseRepositoryProvider)
          .createCase(
            title: _titleController.text.trim(),
            legalTopic: _topicController.text.trim(),
          );
      if (mounted) {
        Navigator.of(context).pop(created);
      }
    } on ApiException catch (e) {
      if (mounted) {
        setState(() => _error = e.message);
      }
    } on Object {
      if (mounted) {
        setState(() => _error = 'Dosya oluşturulamadı.');
      }
    } finally {
      if (mounted) {
        setState(() => _busy = false);
      }
    }
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
          Text('Yeni Dosya', style: theme.textTheme.titleLarge),
          const SizedBox(height: AppConstants.spacingMd),
          TextField(
            controller: _titleController,
            enabled: !_busy,
            textInputAction: TextInputAction.next,
            decoration: const InputDecoration(
              labelText: 'Başlık',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: AppConstants.spacingMd),
          TextField(
            controller: _topicController,
            enabled: !_busy,
            textInputAction: TextInputAction.done,
            onSubmitted: (_) => _submit(),
            decoration: const InputDecoration(
              labelText: 'Hukuk alanı (isteğe bağlı)',
              border: OutlineInputBorder(),
            ),
          ),
          if (_error != null) ...<Widget>[
            const SizedBox(height: AppConstants.spacingMd),
            Text(
              _error!,
              style: theme.textTheme.bodyMedium?.copyWith(
                color: theme.colorScheme.error,
              ),
            ),
          ],
          const SizedBox(height: AppConstants.spacingLg),
          FilledButton(
            onPressed: _busy ? null : _submit,
            child: _busy
                ? const SizedBox(
                    height: 20,
                    width: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Text('Oluştur'),
          ),
        ],
      ),
    );
  }
}
