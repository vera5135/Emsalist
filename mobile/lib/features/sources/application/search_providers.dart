import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../auth/application/auth_providers.dart';
import '../data/search_api.dart';
import '../data/search_repository.dart';

final Provider<SearchApi> searchApiProvider = Provider<SearchApi>((ref) {
  return SearchApi(ref.watch(authenticatedApiClientProvider));
});

final Provider<SearchRepository> searchRepositoryProvider =
    Provider<SearchRepository>((ref) {
      return SearchRepository(ref.watch(searchApiProvider));
    });

final StateProvider<String> searchQueryProvider = StateProvider<String>(
  (ref) => '',
);

final FutureProviderFamily<List<SearchResultItem>, String> searchResultsProvider =
    FutureProvider.family<List<SearchResultItem>, String>((ref, query) async {
      if (query.isEmpty) return <SearchResultItem>[];
      final SearchResultPage page = await ref
          .watch(searchRepositoryProvider)
          .searchLegal(query: query);
      return page.results;
    });

final FutureProviderFamily<List<SearchResultItem>, String>
    similarResultsProvider = FutureProvider.family<List<SearchResultItem>, String>((
      ref,
      String sourceId,
    ) async {
      final SearchResultPage page = await ref
          .watch(searchRepositoryProvider)
          .searchSimilar(sourceId: sourceId);
      return page.results;
    });

final FutureProviderFamily<List<SearchResultItem>, String>
    opposingResultsProvider = FutureProvider.family<List<SearchResultItem>, String>((
      ref,
      String sourceId,
    ) async {
      final SearchResultPage page = await ref
          .watch(searchRepositoryProvider)
          .searchOpposing(sourceId: sourceId);
      return page.results;
    });

enum SearchMode { legal, similar, opposing }

final StateProvider<SearchMode> searchModeProvider =
    StateProvider<SearchMode>((ref) => SearchMode.legal);

final StateProvider<String> searchSourceIdProvider =
    StateProvider<String>((ref) => '');
