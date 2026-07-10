import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../auth/application/auth_providers.dart';
import '../data/case_api.dart';
import '../data/case_repository.dart';
import '../domain/case_item.dart';

final Provider<CaseApi> caseApiProvider = Provider<CaseApi>((ref) {
  return CaseApi(ref.watch(authenticatedApiClientProvider));
});

final Provider<CaseRepository> caseRepositoryProvider = Provider<CaseRepository>(
  (ref) {
    return CaseRepository(ref.watch(caseApiProvider));
  },
);

/// Active (non-archived) cases.
final FutureProvider<List<CaseItem>> activeCasesProvider =
    FutureProvider<List<CaseItem>>((ref) async {
      return ref.watch(caseRepositoryProvider).listCases(archived: false);
    });

/// Archived cases.
final FutureProvider<List<CaseItem>> archivedCasesProvider =
    FutureProvider<List<CaseItem>>((ref) async {
      return ref.watch(caseRepositoryProvider).listCases(archived: true);
    });

/// The currently selected case id (drives the chat screen). Null until chosen.
class ActiveCaseNotifier extends StateNotifier<String?> {
  ActiveCaseNotifier() : super(null);

  void select(String caseId) => state = caseId;
  void clear() => state = null;
}

final StateNotifierProvider<ActiveCaseNotifier, String?> activeCaseIdProvider =
    StateNotifierProvider<ActiveCaseNotifier, String?>(
      (ref) => ActiveCaseNotifier(),
    );

/// Detail for a single case.
final FutureProviderFamily<CaseItem, String> caseDetailProvider =
    FutureProvider.family<CaseItem, String>((ref, String caseId) async {
      return ref.watch(caseRepositoryProvider).getCase(caseId);
    });
