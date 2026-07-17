import '../domain/draft_item.dart';
import 'draft_api.dart';
import 'models/draft_dto.dart';

class DraftRepository {
  const DraftRepository(this._api);

  final DraftApi _api;

  Future<List<DraftItem>> listDrafts(String caseId) async {
    final dto = await _api.listDrafts(caseId);
    return dto.items.map(DraftItem.fromDto).toList();
  }

  Future<DraftCreateResultItem> createDraft(
    String caseId, {
    required String title,
    required String draftType,
    String? supersedesDraftId,
  }) async {
    final dto = await _api.createDraft(
      caseId,
      title: title,
      draftType: draftType,
      supersedesDraftId: supersedesDraftId,
    );
    return DraftCreateResultItem.fromDto(dto);
  }

  Future<DraftDetailItem> getDraft(String caseId, String draftId) async {
    final dto = await _api.getDraft(caseId, draftId);
    return DraftDetailItem.fromDto(dto);
  }

  Future<DraftItem> updateDraft(
    String caseId,
    String draftId, {
    required int version,
    String? title,
    String? status,
  }) async {
    final dto = await _api.updateDraft(
      caseId,
      draftId,
      version: version,
      title: title,
      status: status,
    );
    return DraftItem.fromDto(dto);
  }

  Future<void> deleteDraft(String caseId, String draftId) {
    return _api.deleteDraft(caseId, draftId);
  }

  Future<DraftParagraphItem> createParagraph(
    String caseId,
    String draftId, {
    required int order,
    required String paragraphType,
    required String text,
  }) async {
    final dto = await _api.createParagraph(
      caseId,
      draftId,
      order: order,
      paragraphType: paragraphType,
      text: text,
    );
    return DraftParagraphItem.fromDto(dto);
  }

  Future<DraftParagraphItem> updateParagraph(
    String caseId,
    String draftId,
    String paragraphId, {
    required int version,
    String? text,
    String? paragraphType,
    int? order,
    String? verificationStatus,
  }) async {
    final dto = await _api.updateParagraph(
      caseId,
      draftId,
      paragraphId,
      version: version,
      text: text,
      paragraphType: paragraphType,
      order: order,
      verificationStatus: verificationStatus,
    );
    return DraftParagraphItem.fromDto(dto);
  }

  Future<DraftIssueLinkItem> addIssueLink(
    String caseId,
    String draftId,
    String paragraphId,
    String legalIssueId,
  ) async {
    final dto = await _api.addIssueLink(
      caseId,
      draftId,
      paragraphId,
      legalIssueId,
    );
    return DraftIssueLinkItem.fromDto(dto);
  }

  Future<DraftSourceLinkItem> addSourceLink(
    String caseId,
    String draftId,
    String paragraphId, {
    required String sourceRecordId,
    required String sourceVersionId,
    String? sourceParagraphId,
    required String usageType,
    required String quoteHash,
  }) async {
    final dto = await _api.addSourceLink(
      caseId,
      draftId,
      paragraphId,
      sourceRecordId: sourceRecordId,
      sourceVersionId: sourceVersionId,
      sourceParagraphId: sourceParagraphId,
      usageType: usageType,
      quoteHash: quoteHash,
    );
    return DraftSourceLinkItem.fromDto(dto);
  }

  Future<DraftReadinessItem> checkReadiness(
    String caseId,
    String draftId,
  ) async {
    final dto = await _api.checkReadiness(caseId, draftId);
    return DraftReadinessItem.fromDto(dto);
  }

  Future<DraftPlanItem> getPlan(String caseId, String draftId) async {
    final dto = await _api.getPlan(caseId, draftId);
    return DraftPlanItem.fromDto(dto);
  }

  Future<DraftValidationItem> validateDraft(
    String caseId,
    String draftId,
  ) async {
    final dto = await _api.validateDraft(caseId, draftId);
    return DraftValidationItem.fromDto(dto);
  }

  Future<DraftFinalizeItem> finalizeDraft(
    String caseId,
    String draftId, {
    required int version,
  }) async {
    final dto = await _api.finalizeDraft(
      caseId,
      draftId,
      version: version,
    );
    return DraftFinalizeItem.fromDto(dto);
  }

  Future<DraftRevisionActionDto> editParagraph(
    String caseId,
    String draftId,
    String paragraphId, {
    required int draftVersion,
    required int paragraphVersion,
    required String text,
  }) {
    return _api.editParagraph(
      caseId,
      draftId,
      paragraphId,
      draftVersion: draftVersion,
      paragraphVersion: paragraphVersion,
      text: text,
    );
  }

  Future<DraftReviewActionDto> acceptParagraph(
    String caseId,
    String draftId,
    String paragraphId, {
    required int draftVersion,
    required int paragraphVersion,
    required String revisionId,
  }) {
    return _api.acceptParagraph(
      caseId,
      draftId,
      paragraphId,
      draftVersion: draftVersion,
      paragraphVersion: paragraphVersion,
      revisionId: revisionId,
    );
  }

  Future<DraftReviewActionDto> requestChanges(
    String caseId,
    String draftId,
    String paragraphId, {
    required int draftVersion,
    required int paragraphVersion,
    required String revisionId,
    required String reasonCode,
  }) {
    return _api.requestChanges(
      caseId,
      draftId,
      paragraphId,
      draftVersion: draftVersion,
      paragraphVersion: paragraphVersion,
      revisionId: revisionId,
      reasonCode: reasonCode,
    );
  }

  Future<List<DraftRevisionItem>> listRevisions(
    String caseId,
    String draftId,
    String paragraphId,
  ) async {
    final list = await _api.listRevisions(caseId, draftId, paragraphId);
    return list.map(DraftRevisionItem.fromDto).toList();
  }

  Future<DraftRevisionActionDto> restoreRevision(
    String caseId,
    String draftId,
    String paragraphId, {
    required String revisionId,
    required int draftVersion,
    required int paragraphVersion,
  }) {
    return _api.restoreRevision(
      caseId,
      draftId,
      paragraphId,
      revisionId: revisionId,
      draftVersion: draftVersion,
      paragraphVersion: paragraphVersion,
    );
  }

  Future<List<DraftReviewEventItem>> listReviews(
    String caseId,
    String draftId,
    String paragraphId,
  ) async {
    final list = await _api.listReviews(caseId, draftId, paragraphId);
    return list.map(DraftReviewEventItem.fromDto).toList();
  }

  Future<DraftGenerationJobItem> enqueueGenerationJob(
    String caseId,
    String draftId, {
    required int draftVersion,
    required String clientRequestId,
    List<String>? selectedIssueIds,
    List<String>? selectedSourceUsageIds,
  }) async {
    final dto = await _api.enqueueGenerationJob(
      caseId,
      draftId,
      draftVersion: draftVersion,
      clientRequestId: clientRequestId,
      selectedIssueIds: selectedIssueIds,
      selectedSourceUsageIds: selectedSourceUsageIds,
    );
    return DraftGenerationJobItem.fromDto(dto);
  }

  Future<DraftGenerationJobItem> getGenerationJob(
    String caseId,
    String draftId,
    String jobId,
  ) async {
    final dto = await _api.getGenerationJob(caseId, draftId, jobId);
    return DraftGenerationJobItem.fromDto(dto);
  }
}
