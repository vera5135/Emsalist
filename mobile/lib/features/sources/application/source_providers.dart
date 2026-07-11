import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../auth/application/auth_providers.dart';
import '../data/source_api.dart';
import '../data/source_repository.dart';
import '../domain/source_item.dart';

final Provider<SourceApi> sourceApiProvider = Provider<SourceApi>((ref) {
  return SourceApi(ref.watch(authenticatedApiClientProvider));
});

final Provider<SourceRepository> sourceRepositoryProvider =
    Provider<SourceRepository>((ref) {
      return SourceRepository(ref.watch(sourceApiProvider));
    });

/// Global legal source catalog.
final FutureProvider<List<SourceRecordItem>> sourcesProvider =
    FutureProvider<List<SourceRecordItem>>((ref) async {
      return ref.watch(sourceRepositoryProvider).listSources();
    });

/// Sources used within a specific case.
final FutureProviderFamily<List<CaseSourceUsage>, String> caseSourcesProvider =
    FutureProvider.family<List<CaseSourceUsage>, String>((ref, String caseId) async {
      return ref.watch(sourceRepositoryProvider).caseSources(caseId);
    });

/// Official source tracking overview.
final FutureProvider<List<OfficialTrackingItem>> officialTrackingProvider =
    FutureProvider<List<OfficialTrackingItem>>((ref) async {
      return ref.watch(sourceRepositoryProvider).officialTracking();
    });
