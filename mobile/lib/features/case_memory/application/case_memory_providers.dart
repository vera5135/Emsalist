import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../auth/application/auth_providers.dart';
import '../data/case_memory_api.dart';
import '../data/case_memory_repository.dart';
import '../domain/case_memory.dart';

final Provider<CaseMemoryApi> caseMemoryApiProvider = Provider<CaseMemoryApi>((
  ref,
) {
  return CaseMemoryApi(ref.watch(authenticatedApiClientProvider));
});

final Provider<CaseMemoryRepository> caseMemoryRepositoryProvider =
    Provider<CaseMemoryRepository>((ref) {
      return CaseMemoryRepository(ref.watch(caseMemoryApiProvider));
    });

/// The structured memory for a case; refetched per case id.
final FutureProviderFamily<CaseMemory, String> caseMemoryProvider =
    FutureProvider.family<CaseMemory, String>((ref, String caseId) async {
      return ref.watch(caseMemoryRepositoryProvider).loadMemory(caseId);
    });
