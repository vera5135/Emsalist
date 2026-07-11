import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/constants/app_constants.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/widgets/state_widgets.dart';
import '../application/source_providers.dart';
import '../domain/source_item.dart';

/// Global legal sources catalog: verification + temporal status per card, with
/// a detail view showing citable paragraphs. No parser/index/relevance internals
/// are shown to the user.
class SourcesScreen extends ConsumerWidget {
  const SourcesScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final AsyncValue<List<SourceRecordItem>> sources = ref.watch(sourcesProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Kaynaklar'),
        actions: <Widget>[
          IconButton(
            icon: const Icon(Icons.track_changes_outlined),
            tooltip: 'Resmî Kaynak Takibi',
            onPressed: () => Navigator.of(context).push<void>(
              MaterialPageRoute<void>(
                builder: (BuildContext ctx) => const OfficialTrackingScreen(),
              ),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: 'Yenile',
            onPressed: () => ref.invalidate(sourcesProvider),
          ),
        ],
      ),
      body: sources.when(
        loading: () => const LoadingWidget(message: 'Kaynaklar yükleniyor'),
        error: (Object error, _) => AppErrorWidget(
          message: error is ApiException ? error.message : 'Kaynaklar yüklenemedi.',
          onRetry: () => ref.invalidate(sourcesProvider),
        ),
        data: (List<SourceRecordItem> items) {
          if (items.isEmpty) {
            return const EmptyWidget(
              title: 'Henüz kaynak yok',
              message: 'Doğrulanmış hukuki kaynaklar burada görünecek.',
              icon: Icons.menu_book_outlined,
            );
          }
          return RefreshIndicator(
            onRefresh: () async {
              ref.invalidate(sourcesProvider);
              await ref.read(sourcesProvider.future);
            },
            child: ListView.builder(
              itemCount: items.length,
              itemBuilder: (BuildContext context, int index) =>
                  SourceCard(item: items[index]),
            ),
          );
        },
      ),
    );
  }
}

Color verificationColor(BuildContext context, String status) {
  final ColorScheme scheme = Theme.of(context).colorScheme;
  switch (status) {
    case 'verified_official':
    case 'editor_verified':
      return scheme.primary;
    case 'verified_secondary':
      return scheme.tertiary;
    case 'conflicting':
    case 'quarantined':
    case 'repealed':
      return scheme.error;
    default:
      return scheme.onSurfaceVariant;
  }
}

IconData verificationIcon(String status) {
  switch (status) {
    case 'verified_official':
    case 'editor_verified':
      return Icons.verified_outlined;
    case 'verified_secondary':
      return Icons.check_circle_outline;
    case 'conflicting':
      return Icons.error_outline;
    case 'quarantined':
    case 'repealed':
      return Icons.block;
    case 'superseded':
    case 'outdated':
      return Icons.history;
    default:
      return Icons.help_outline;
  }
}

class SourceCard extends StatelessWidget {
  const SourceCard({required this.item, super.key});

  final SourceRecordItem item;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final String subtitle = <String>[
      if (item.court.isNotEmpty) item.court,
      if (item.chamber.isNotEmpty) item.chamber,
      if (item.decisionDate.isNotEmpty) item.decisionDate,
    ].join(' · ');
    return Card(
      child: ListTile(
        title: Text(item.displayTitle),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            if (subtitle.isNotEmpty) Text(subtitle),
            const SizedBox(height: AppConstants.spacingXs),
            Row(
              children: <Widget>[
                Icon(
                  verificationIcon(item.verificationStatus),
                  size: 14,
                  color: verificationColor(context, item.verificationStatus),
                ),
                const SizedBox(width: AppConstants.spacingXs),
                Flexible(
                  child: Text(
                    item.badge,
                    style: theme.textTheme.labelSmall?.copyWith(
                      color: verificationColor(context, item.verificationStatus),
                    ),
                  ),
                ),
                if (item.isOfficial) ...<Widget>[
                  const SizedBox(width: AppConstants.spacingSm),
                  Icon(Icons.gavel_outlined, size: 12, color: theme.colorScheme.primary),
                ],
              ],
            ),
          ],
        ),
        onTap: () => Navigator.of(context).push<void>(
          MaterialPageRoute<void>(
            builder: (BuildContext ctx) => SourceDetailScreen(sourceId: item.id),
          ),
        ),
      ),
    );
  }
}

class SourceDetailScreen extends ConsumerWidget {
  const SourceDetailScreen({required this.sourceId, super.key});

  final String sourceId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final ThemeData theme = Theme.of(context);
    final AsyncValue<SourceRecordItem> source = ref.watch(
      FutureProvider.autoDispose<SourceRecordItem>(
        (ref) => ref.watch(sourceRepositoryProvider).getSource(sourceId),
      ),
    );
    return Scaffold(
      appBar: AppBar(title: const Text('Kaynak Detayı')),
      body: source.when(
        loading: () => const LoadingWidget(message: 'Kaynak yükleniyor'),
        error: (Object e, _) => AppErrorWidget(
          message: e is ApiException ? e.message : 'Kaynak yüklenemedi.',
        ),
        data: (SourceRecordItem item) {
          final AsyncValue<List<SourceParagraphItem>> paras = ref.watch(
            FutureProvider.autoDispose<List<SourceParagraphItem>>(
              (ref) => ref.watch(sourceRepositoryProvider).paragraphs(sourceId),
            ),
          );
          return ListView(
            padding: const EdgeInsets.all(AppConstants.spacingMd),
            children: <Widget>[
              Text(item.displayTitle, style: theme.textTheme.titleLarge),
              const SizedBox(height: AppConstants.spacingSm),
              Row(
                children: <Widget>[
                  Icon(verificationIcon(item.verificationStatus),
                      size: 16, color: verificationColor(context, item.verificationStatus)),
                  const SizedBox(width: AppConstants.spacingXs),
                  Text(item.badge,
                      style: theme.textTheme.labelMedium?.copyWith(
                          color: verificationColor(context, item.verificationStatus))),
                ],
              ),
              Text('Güncellik: ${temporalStatusLabel(item.temporalStatus)}',
                  style: theme.textTheme.bodySmall),
              if (item.caseNumber.isNotEmpty)
                Text('Esas/Karar: ${item.caseNumber} / ${item.decisionNumber}',
                    style: theme.textTheme.bodySmall),
              const Divider(height: AppConstants.spacingLg),
              Text('Atıf Yapılabilir Bölümler', style: theme.textTheme.titleMedium),
              const SizedBox(height: AppConstants.spacingSm),
              paras.when(
                loading: () => const Padding(
                  padding: EdgeInsets.all(AppConstants.spacingMd),
                  child: LoadingWidget(),
                ),
                error: (Object e, _) => const Text('Bölümler yüklenemedi.'),
                data: (List<SourceParagraphItem> list) {
                  if (list.isEmpty) {
                    return const Text('Kayıtlı bölüm yok.');
                  }
                  return Column(
                    children: list.map((SourceParagraphItem p) {
                      final String label = p.articleNumber.isNotEmpty
                          ? 'Madde ${p.articleNumber}'
                          : (p.page != null ? 'Sayfa ${p.page}' : 'Bölüm ${p.paragraphIndex}');
                      return Card(
                        child: ListTile(
                          title: Text(label, style: theme.textTheme.labelLarge),
                          subtitle: Text(
                            p.text,
                            maxLines: 6,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      );
                    }).toList(),
                  );
                },
              ),
            ],
          );
        },
      ),
    );
  }
}

/// Official source tracking overview (non-technical, user-facing).
class OfficialTrackingScreen extends ConsumerWidget {
  const OfficialTrackingScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final ThemeData theme = Theme.of(context);
    final AsyncValue<List<OfficialTrackingItem>> tracking =
        ref.watch(officialTrackingProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Resmî Kaynak Takibi')),
      body: tracking.when(
        loading: () => const LoadingWidget(message: 'Takip bilgileri yükleniyor'),
        error: (Object e, _) => AppErrorWidget(
          message: e is ApiException ? e.message : 'Takip bilgileri yüklenemedi.',
          onRetry: () => ref.invalidate(officialTrackingProvider),
        ),
        data: (List<OfficialTrackingItem> items) {
          if (items.isEmpty) {
            return const EmptyWidget(
              title: 'Takip edilen kaynak yok',
              message: 'Resmî kaynaklar eklendikçe burada izlenecek.',
              icon: Icons.track_changes_outlined,
            );
          }
          return RefreshIndicator(
            onRefresh: () async {
              ref.invalidate(officialTrackingProvider);
              await ref.read(officialTrackingProvider.future);
            },
            child: ListView.builder(
              itemCount: items.length,
              itemBuilder: (BuildContext context, int index) {
                final OfficialTrackingItem t = items[index];
                return Card(
                  child: ListTile(
                    leading: Icon(
                      t.requiresReview ? Icons.rate_review_outlined : Icons.check_circle_outline,
                      color: t.requiresReview ? theme.colorScheme.error : theme.colorScheme.primary,
                    ),
                    title: Text(t.displayTitle),
                    subtitle: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Text(t.lastCheckedAt == null
                            ? 'Henüz kontrol edilmedi'
                            : 'Son kontrol: ${t.lastCheckedAt}'),
                        if (t.newVersionDetected)
                          Text('Yeni sürüm mevcut',
                              style: theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.error)),
                        if (t.affectedCaseCount > 0)
                          Text('Etkilenen dosya: ${t.affectedCaseCount}',
                              style: theme.textTheme.labelSmall),
                        if (t.requiresReview)
                          Text('Yeniden inceleme gerekli',
                              style: theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.error)),
                      ],
                    ),
                  ),
                );
              },
            ),
          );
        },
      ),
    );
  }
}

/// Sources used within a specific case (reached from the case/chat context).
class CaseSourcesScreen extends ConsumerWidget {
  const CaseSourcesScreen({required this.caseId, super.key});

  final String caseId;

  Future<void> _remove(WidgetRef ref, String usageId) async {
    await ref.read(sourceRepositoryProvider).removeCaseSource(caseId, usageId);
    ref.invalidate(caseSourcesProvider(caseId));
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final ThemeData theme = Theme.of(context);
    final AsyncValue<List<CaseSourceUsage>> usages =
        ref.watch(caseSourcesProvider(caseId));
    return Scaffold(
      appBar: AppBar(title: const Text('Dosyada Kullanılan Kaynaklar')),
      body: usages.when(
        loading: () => const LoadingWidget(message: 'Kaynaklar yükleniyor'),
        error: (Object e, _) => AppErrorWidget(
          message: e is ApiException ? e.message : 'Kaynaklar yüklenemedi.',
          onRetry: () => ref.invalidate(caseSourcesProvider(caseId)),
        ),
        data: (List<CaseSourceUsage> items) {
          if (items.isEmpty) {
            return const EmptyWidget(
              title: 'Bu dosyada kaynak yok',
              message: 'Doğrulanmış kaynaklar dosyaya eklendikçe burada görünür.',
              icon: Icons.link_outlined,
            );
          }
          return RefreshIndicator(
            onRefresh: () async {
              ref.invalidate(caseSourcesProvider(caseId));
              await ref.read(caseSourcesProvider(caseId).future);
            },
            child: ListView.builder(
              itemCount: items.length,
              itemBuilder: (BuildContext context, int index) {
                final CaseSourceUsage u = items[index];
                return Card(
                  child: ListTile(
                    title: Text(u.displayTitle),
                    subtitle: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        if (u.reason.isNotEmpty)
                          Text('Neden: ${u.reason}', style: theme.textTheme.bodySmall),
                        if (u.selectedParagraph.isNotEmpty)
                          Text(u.selectedParagraph,
                              maxLines: 3, overflow: TextOverflow.ellipsis,
                              style: theme.textTheme.bodySmall),
                        const SizedBox(height: AppConstants.spacingXs),
                        Row(
                          children: <Widget>[
                            Icon(verificationIcon(u.verificationStatus),
                                size: 14, color: verificationColor(context, u.verificationStatus)),
                            const SizedBox(width: AppConstants.spacingXs),
                            Flexible(child: Text(u.badge, style: theme.textTheme.labelSmall)),
                          ],
                        ),
                        if (u.usedInFinalDraft)
                          Text('Dilekçede kullanıldı',
                              style: theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.primary)),
                      ],
                    ),
                    trailing: IconButton(
                      icon: const Icon(Icons.delete_outline),
                      tooltip: 'Kaldır',
                      onPressed: () => _remove(ref, u.id),
                    ),
                  ),
                );
              },
            ),
          );
        },
      ),
    );
  }
}
