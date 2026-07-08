import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/constants/app_constants.dart';
import '../../core/models/case_model.dart';
import '../../core/providers/case_provider.dart';

class CaseDrawer extends ConsumerWidget {
  const CaseDrawer({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final ThemeData theme = Theme.of(context);
    final CaseState caseState = ref.watch(caseProvider);

    return Drawer(
      child: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Padding(
              padding: const EdgeInsets.all(AppConstants.spacingMd),
              child: Semantics(
                button: true,
                label: 'Yeni dosya oluştur',
                child: FilledButton.icon(
                  onPressed: () {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(
                        content: Text('Yeni dosya henüz uygulanmadı'),
                      ),
                    );
                  },
                  icon: const Icon(Icons.add),
                  label: const Text('Yeni Dosya'),
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(
                horizontal: AppConstants.spacingMd,
              ),
              child: TextField(
                decoration: InputDecoration(
                  hintText: 'Dosya ara…',
                  prefixIcon: const Icon(Icons.search),
                  isDense: true,
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(AppConstants.radiusMd),
                  ),
                ),
              ),
            ),
            const SizedBox(height: AppConstants.spacingSm),
            Expanded(
              child: ListView(
                children: <Widget>[
                  _Section(
                    title: 'Sabitlenenler',
                    cases: caseState.pinned,
                    activeCaseId: caseState.activeCase?.id,
                    onTap: (String id) => _select(context, ref, id),
                  ),
                  _Section(
                    title: 'Son Dosyalar',
                    cases: caseState.recent,
                    activeCaseId: caseState.activeCase?.id,
                    onTap: (String id) => _select(context, ref, id),
                  ),
                  _Section(
                    title: 'Arşiv',
                    cases: caseState.archived,
                    activeCaseId: caseState.activeCase?.id,
                    onTap: (String id) => _select(context, ref, id),
                  ),
                ],
              ),
            ),
            Divider(height: 1, color: theme.colorScheme.outlineVariant),
            ListTile(
              leading: const Icon(Icons.settings_outlined),
              title: const Text('Ayarlar'),
              onTap: () => Navigator.of(context).pop(),
            ),
          ],
        ),
      ),
    );
  }

  void _select(BuildContext context, WidgetRef ref, String id) {
    ref.read(caseProvider.notifier).selectCase(id);
    Navigator.of(context).pop();
  }
}

class _Section extends StatelessWidget {
  const _Section({
    required this.title,
    required this.cases,
    required this.activeCaseId,
    required this.onTap,
  });

  final String title;
  final List<CaseModel> cases;
  final String? activeCaseId;
  final ValueChanged<String> onTap;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    if (cases.isEmpty) {
      return const SizedBox.shrink();
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Padding(
          padding: const EdgeInsets.fromLTRB(
            AppConstants.spacingMd,
            AppConstants.spacingMd,
            AppConstants.spacingMd,
            AppConstants.spacingXs,
          ),
          child: Text(
            title,
            style: theme.textTheme.labelMedium?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
        ...cases.map((CaseModel c) {
          final bool active = c.id == activeCaseId;
          return Semantics(
            selected: active,
            button: true,
            label: 'Dosya ${c.title}, ${c.legalTopic}',
            child: ListTile(
              selected: active,
              selectedTileColor: theme.colorScheme.primary.withValues(
                alpha: 0.10,
              ),
              leading: Icon(
                c.pinned ? Icons.push_pin_outlined : Icons.folder_outlined,
              ),
              title: Text(c.title),
              subtitle: Text(c.legalTopic),
              onTap: () => onTap(c.id),
            ),
          );
        }),
      ],
    );
  }
}
