import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../auth/application/auth_providers.dart';
import '../data/draft_api.dart';
import '../data/draft_repository.dart';
import '../domain/draft_item.dart';

final Provider<DraftApi> draftApiProvider = Provider<DraftApi>((ref) {
  return DraftApi(ref.watch(authenticatedApiClientProvider));
});

final Provider<DraftRepository> draftRepositoryProvider =
    Provider<DraftRepository>((ref) {
  return DraftRepository(ref.watch(draftApiProvider));
});

final FutureProviderFamily<List<DraftItem>, String> caseDraftsProvider =
    FutureProvider.family<List<DraftItem>, String>((ref, String caseId) async {
  return ref.watch(draftRepositoryProvider).listDrafts(caseId);
});

final FutureProviderFamily<DraftDetailItem, ({String caseId, String draftId})>
    draftDetailProvider =
    FutureProvider.family<DraftDetailItem, ({String caseId, String draftId})>((
  ref,
  record,
) async {
  return ref
      .watch(draftRepositoryProvider)
      .getDraft(record.caseId, record.draftId);
});

final FutureProviderFamily<
    DraftReadinessItem,
    ({String caseId, String draftId})> draftReadinessProvider =
    FutureProvider.family<DraftReadinessItem, ({String caseId, String draftId})>(
  (ref, record) async {
    return ref
        .watch(draftRepositoryProvider)
        .checkReadiness(record.caseId, record.draftId);
  },
);

final FutureProviderFamily<DraftPlanItem, ({String caseId, String draftId})>
    draftPlanProvider =
    FutureProvider.family<DraftPlanItem, ({String caseId, String draftId})>((
  ref,
  record,
) async {
  return ref
      .watch(draftRepositoryProvider)
      .getPlan(record.caseId, record.draftId);
});

final FutureProviderFamily<DraftValidationItem, ({String caseId, String draftId})>
    draftValidationProvider =
    FutureProvider.family<DraftValidationItem, ({String caseId, String draftId})>(
  (ref, record) async {
    return ref
        .watch(draftRepositoryProvider)
        .validateDraft(record.caseId, record.draftId);
  },
);

final FutureProviderFamily<
    List<DraftRevisionItem>,
    ({String caseId, String draftId, String paragraphId})>
    draftRevisionsProvider = FutureProvider.family<
        List<DraftRevisionItem>,
        ({String caseId, String draftId, String paragraphId})>((
  ref,
  record,
) async {
  return ref.watch(draftRepositoryProvider).listRevisions(
        record.caseId,
        record.draftId,
        record.paragraphId,
      );
});

final FutureProviderFamily<
    List<DraftReviewEventItem>,
    ({String caseId, String draftId, String paragraphId})>
    draftReviewsProvider = FutureProvider.family<
        List<DraftReviewEventItem>,
        ({String caseId, String draftId, String paragraphId})>((
  ref,
  record,
) async {
  return ref.watch(draftRepositoryProvider).listReviews(
        record.caseId,
        record.draftId,
        record.paragraphId,
      );
});
