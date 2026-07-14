import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/constants/app_constants.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/widgets/state_widgets.dart';
import '../../cases/application/case_providers.dart';
import '../application/search_providers.dart';
import '../application/source_providers.dart';
import '../data/search_repository.dart';
import '../domain/source_item.dart';

class SearchScreen extends ConsumerStatefulWidget {
  const SearchScreen({super.key});

  @override
  ConsumerState<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends ConsumerState<SearchScreen> {
  final TextEditingController _searchController = TextEditingController();
  Timer? _debounceTimer;

  @override
  void initState() {
    super.initState();
    _searchController.addListener(_onTextChanged);
  }

  @override
  void dispose() {
    _debounceTimer?.cancel();
    _searchController.removeListener(_onTextChanged);
    _searchController.dispose();
    super.dispose();
  }

  void _onTextChanged() {
    _debounceTimer?.cancel();
    _debounceTimer = Timer(const Duration(milliseconds: 500), () {
      final String query = _searchController.text.trim();
      ref.read(searchQueryProvider.notifier).state = query;
    });
  }

  void _submit() {
    _debounceTimer?.cancel();
    final String query = _searchController.text.trim();
    ref.read(searchQueryProvider.notifier).state = query;
  }

  @override
  Widget build(BuildContext context) {
    final SearchMode searchMode = ref.watch(searchModeProvider);
    final String query = ref.watch(searchQueryProvider);
    final String sourceId = ref.watch(searchSourceIdProvider);

    return Scaffold(
      appBar: AppBar(
        title: SizedBox(
          height: 40,
          child: TextField(
            controller: _searchController,
            autofocus: true,
            textInputAction: TextInputAction.search,
            decoration: InputDecoration(
              hintText: 'Karar, kanun, madde ara...',
              prefixIcon: const Icon(Icons.search, size: 20),
              suffixIcon: _searchController.text.isNotEmpty
                  ? IconButton(
                      icon: const Icon(Icons.clear, size: 20),
                      onPressed: () {
                        _searchController.clear();
                        ref.read(searchQueryProvider.notifier).state = '';
                      },
                    )
                  : null,
              border: InputBorder.none,
              contentPadding: const EdgeInsets.symmetric(vertical: 8),
            ),
            style: const TextStyle(fontSize: 16),
            onSubmitted: (_) => _submit(),
          ),
        ),
        titleSpacing: 0,
        leading: searchMode != SearchMode.legal
            ? IconButton(
                icon: const Icon(Icons.arrow_back),
                onPressed: () {
                  ref.read(searchModeProvider.notifier).state =
                      SearchMode.legal;
                  ref.read(searchSourceIdProvider.notifier).state = '';
                  ref.read(searchQueryProvider.notifier).state = '';
                  _searchController.clear();
                },
              )
            : null,
      ),
      body: _buildBody(context, ref, searchMode, query, sourceId),
    );
  }

  Widget _buildBody(
    BuildContext context,
    WidgetRef ref,
    SearchMode searchMode,
    String query,
    String sourceId,
  ) {
    if (searchMode == SearchMode.legal) {
      return _buildLegalResults(context, ref, query);
    } else if (searchMode == SearchMode.similar) {
      return _buildFamilyResults(
        context,
        ref,
        sourceId,
        'Benzer kararlar yükleniyor',
        'Benzer karar bulunamadı',
        similarResultsProvider,
      );
    } else {
      return _buildFamilyResults(
        context,
        ref,
        sourceId,
        'Karşıt kararlar yükleniyor',
        'Karşıt karar bulunamadı',
        opposingResultsProvider,
      );
    }
  }

  Widget _buildLegalResults(BuildContext context, WidgetRef ref, String query) {
    if (query.isEmpty) {
      return const EmptyWidget(
        title: 'Arama',
        message: 'Aramak istediğiniz karar, kanun veya maddeyi yazın.',
        icon: Icons.search_outlined,
      );
    }

    final AsyncValue<List<SearchResultItem>> results = ref.watch(
      searchResultsProvider(query),
    );

    return results.when(
      loading: () => const LoadingWidget(message: 'Aranıyor'),
      error: (Object error, _) => AppErrorWidget(
        message: error is ApiException ? error.message : 'Arama yapılamadı.',
        onRetry: () => ref.invalidate(searchResultsProvider(query)),
      ),
      data: (List<SearchResultItem> items) {
        if (items.isEmpty) {
          return const EmptyWidget(
            title: 'Arama sonucu bulunamadı',
            message: 'Farklı anahtar kelimelerle tekrar deneyin.',
            icon: Icons.search_off_outlined,
          );
        }
        return ListView.builder(
          padding: const EdgeInsets.only(bottom: AppConstants.spacingLg + 80),
          itemCount: items.length,
          itemBuilder: (BuildContext context, int index) =>
              SearchResultCard(item: items[index]),
        );
      },
    );
  }

  Widget _buildFamilyResults(
    BuildContext context,
    WidgetRef ref,
    String sourceId,
    String loadingMessage,
    String emptyMessage,
    FutureProviderFamily<List<SearchResultItem>, String> provider,
  ) {
    if (sourceId.isEmpty) {
      return const LoadingWidget();
    }

    final AsyncValue<List<SearchResultItem>> results = ref.watch(
      provider(sourceId),
    );

    return results.when(
      loading: () => LoadingWidget(message: loadingMessage),
      error: (Object error, _) => AppErrorWidget(
        message: error is ApiException
            ? error.message
            : 'Sonuçlar yüklenemedi.',
        onRetry: () => ref.invalidate(provider(sourceId)),
      ),
      data: (List<SearchResultItem> items) {
        if (items.isEmpty) {
          return EmptyWidget(
            title: emptyMessage,
            message: 'Farklı bir kaynakla tekrar deneyin.',
            icon: Icons.search_off_outlined,
          );
        }
        return ListView.builder(
          padding: const EdgeInsets.only(bottom: AppConstants.spacingLg + 80),
          itemCount: items.length,
          itemBuilder: (BuildContext context, int index) =>
              SearchResultCard(item: items[index]),
        );
      },
    );
  }
}

Color _scoreColor(ThemeData theme, double score) {
  if (score >= 0.8) return theme.colorScheme.primary;
  if (score >= 0.5) return theme.colorScheme.tertiary;
  return theme.colorScheme.onSurfaceVariant;
}

class SearchResultCard extends ConsumerWidget {
  const SearchResultCard({required this.item, super.key});

  final SearchResultItem item;

  Future<void> _addToCase(WidgetRef ref) async {
    final String? caseId = ref.read(activeCaseIdProvider);
    if (caseId == null) return;
    try {
      await ref
          .read(sourceRepositoryProvider)
          .addCaseSource(
            caseId,
            sourceRecordId: item.sourceId,
            sourceVersionId: item.sourceVersionId,
            sourceParagraphId: item.sourceParagraphId.isNotEmpty
                ? item.sourceParagraphId
                : null,
          );
      ref.invalidate(caseSourcesProvider(caseId));
    } on ApiException {
      // handled silently
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final ThemeData theme = Theme.of(context);
    final String? caseId = ref.watch(activeCaseIdProvider);

    final AsyncValue<List<CaseSourceUsage>> caseSources = caseId != null
        ? ref.watch(caseSourcesProvider(caseId))
        : const AsyncValue.data(<CaseSourceUsage>[]);

    final bool isUsed = caseSources.maybeWhen(
      data: (List<CaseSourceUsage> usages) => usages.any(
        (CaseSourceUsage u) =>
            u.sourceRecordId == item.sourceId &&
            u.sourceVersionId == item.sourceVersionId &&
            (u.sourceParagraphId == null ||
                u.sourceParagraphId!.isEmpty ||
                u.sourceParagraphId == item.sourceParagraphId),
      ),
      orElse: () => false,
    );

    final List<String> subtitleParts = <String>[
      if (item.court != null && item.court!.isNotEmpty) item.court!,
      if (item.chamber != null && item.chamber!.isNotEmpty) item.chamber!,
      if (item.decisionDate != null && item.decisionDate!.isNotEmpty)
        item.decisionDate!,
    ];

    final String? locator =
        item.caseNumber != null && item.caseNumber!.isNotEmpty
        ? 'E:${item.caseNumber} K:${item.decisionNumber ?? ''}'
        : (item.articleNumber != null && item.articleNumber!.isNotEmpty
              ? '${item.articleKind != null && item.articleKind!.isNotEmpty ? '${item.articleKind} ' : ''}Madde ${item.articleNumber}${item.articleLabel != null && item.articleLabel!.isNotEmpty ? ' (${item.articleLabel})' : ''}'
              : null);

    return Card(
      margin: const EdgeInsets.symmetric(
        horizontal: AppConstants.spacingMd,
        vertical: AppConstants.spacingXs,
      ),
      child: Padding(
        padding: const EdgeInsets.all(AppConstants.spacingMd),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Row(
              children: <Widget>[
                Expanded(
                  child: Text(
                    item.displayTitle,
                    style: theme.textTheme.titleSmall,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                const SizedBox(width: AppConstants.spacingSm),
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: AppConstants.spacingSm,
                    vertical: 2,
                  ),
                  decoration: BoxDecoration(
                    color: theme.colorScheme.secondaryContainer,
                    borderRadius: BorderRadius.circular(AppConstants.radiusSm),
                  ),
                  child: Text(
                    item.sourceTypeDisplay,
                    style: theme.textTheme.labelSmall?.copyWith(
                      color: theme.colorScheme.onSecondaryContainer,
                    ),
                  ),
                ),
              ],
            ),
            if (subtitleParts.isNotEmpty) ...[
              const SizedBox(height: AppConstants.spacingXs),
              Text(subtitleParts.join(' · '), style: theme.textTheme.bodySmall),
            ],
            if (locator != null) ...[
              const SizedBox(height: AppConstants.spacingXs),
              Text(locator, style: theme.textTheme.bodySmall),
            ],
            const SizedBox(height: AppConstants.spacingSm),
            Row(
              children: <Widget>[
                Icon(
                  Icons.verified_outlined,
                  size: 14,
                  color: item.isOfficial
                      ? theme.colorScheme.primary
                      : theme.colorScheme.onSurfaceVariant,
                ),
                const SizedBox(width: AppConstants.spacingXs),
                Flexible(
                  child: Text(item.badge, style: theme.textTheme.labelSmall),
                ),
                const Spacer(),
                Icon(
                  Icons.speed,
                  size: 14,
                  color: _scoreColor(theme, item.finalScore),
                ),
                const SizedBox(width: AppConstants.spacingXs),
                Text(
                  item.relevancePercent,
                  style: theme.textTheme.labelSmall?.copyWith(
                    fontWeight: FontWeight.w600,
                    color: _scoreColor(theme, item.finalScore),
                  ),
                ),
              ],
            ),
            if (item.paragraphSnippet != null &&
                item.paragraphSnippet!.isNotEmpty) ...[
              const SizedBox(height: AppConstants.spacingSm),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(AppConstants.spacingSm),
                decoration: BoxDecoration(
                  color: theme.colorScheme.surfaceContainerHighest.withAlpha(
                    80,
                  ),
                  borderRadius: BorderRadius.circular(AppConstants.radiusSm),
                ),
                child: Text(
                  item.paragraphSnippet!.length > 200
                      ? '${item.paragraphSnippet!.substring(0, 200)}...'
                      : item.paragraphSnippet!,
                  style: theme.textTheme.bodySmall?.copyWith(
                    fontStyle: FontStyle.italic,
                  ),
                  maxLines: 4,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
            if (item.matchReasons.isNotEmpty) ...[
              const SizedBox(height: AppConstants.spacingSm),
              Wrap(
                spacing: AppConstants.spacingXs,
                runSpacing: AppConstants.spacingXs,
                children: item.matchReasons.map((String reason) {
                  return Chip(
                    label: Text(reason, style: theme.textTheme.labelSmall),
                    materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                    visualDensity: VisualDensity.compact,
                    backgroundColor: theme.colorScheme.surfaceContainerHigh,
                    side: BorderSide.none,
                    padding: EdgeInsets.zero,
                  );
                }).toList(),
              ),
            ],
            if (item.degradedMode) ...[
              const SizedBox(height: AppConstants.spacingSm),
              Row(
                children: <Widget>[
                  Icon(
                    Icons.info_outline,
                    size: 14,
                    color: theme.colorScheme.error,
                  ),
                  const SizedBox(width: AppConstants.spacingXs),
                  Text(
                    'Anlamsal arama devre dışı',
                    style: theme.textTheme.labelSmall?.copyWith(
                      color: theme.colorScheme.error,
                    ),
                  ),
                ],
              ),
            ],
            const SizedBox(height: AppConstants.spacingSm),
            Row(
              children: <Widget>[
                if (!isUsed)
                  FilledButton.tonalIcon(
                    icon: const Icon(Icons.add_link, size: 18),
                    label: const Text('Dosyaya Ekle'),
                    style: FilledButton.styleFrom(
                      padding: const EdgeInsets.symmetric(
                        horizontal: AppConstants.spacingSm,
                      ),
                      visualDensity: VisualDensity.compact,
                      textStyle: theme.textTheme.labelSmall,
                    ),
                    onPressed: caseId != null ? () => _addToCase(ref) : null,
                  )
                else
                  OutlinedButton(
                    onPressed: null,
                    style: OutlinedButton.styleFrom(
                      padding: const EdgeInsets.symmetric(
                        horizontal: AppConstants.spacingSm,
                      ),
                      visualDensity: VisualDensity.compact,
                      textStyle: theme.textTheme.labelSmall,
                    ),
                    child: const Text('Eklenmiş'),
                  ),
                const Spacer(),
                TextButton.icon(
                  icon: const Icon(Icons.psychology_outlined, size: 18),
                  label: const Text('Benzer'),
                  style: TextButton.styleFrom(
                    padding: const EdgeInsets.symmetric(
                      horizontal: AppConstants.spacingSm,
                    ),
                    visualDensity: VisualDensity.compact,
                    textStyle: theme.textTheme.labelSmall,
                  ),
                  onPressed: () {
                    ref.read(searchModeProvider.notifier).state =
                        SearchMode.similar;
                    ref.read(searchSourceIdProvider.notifier).state =
                        item.sourceId;
                  },
                ),
                TextButton.icon(
                  icon: const Icon(Icons.balance_outlined, size: 18),
                  label: const Text('Karşıt'),
                  style: TextButton.styleFrom(
                    padding: const EdgeInsets.symmetric(
                      horizontal: AppConstants.spacingSm,
                    ),
                    visualDensity: VisualDensity.compact,
                    textStyle: theme.textTheme.labelSmall,
                  ),
                  onPressed: () {
                    ref.read(searchModeProvider.notifier).state =
                        SearchMode.opposing;
                    ref.read(searchSourceIdProvider.notifier).state =
                        item.sourceId;
                  },
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
