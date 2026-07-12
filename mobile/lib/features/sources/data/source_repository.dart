import '../domain/source_item.dart';
import 'source_api.dart';

/// Domain operations over legal sources, paragraphs, case usage and tracking.
class SourceRepository {
  const SourceRepository(this._api);

  final SourceApi _api;

  Future<List<SourceRecordItem>> listSources({
    String? sourceType,
    String? verificationStatus,
  }) async {
    final dto = await _api.listSources(
      sourceType: sourceType,
      verificationStatus: verificationStatus,
    );
    return dto.items.map(SourceRecordItem.fromDto).toList();
  }

  Future<SourceRecordItem> getSource(String sourceId) async {
    return SourceRecordItem.fromDto(await _api.getSource(sourceId));
  }

  Future<List<SourceParagraphItem>> paragraphs(String sourceId) async {
    final list = await _api.listParagraphs(sourceId);
    return list.map(SourceParagraphItem.fromDto).toList();
  }

  Future<List<CaseSourceUsage>> caseSources(String caseId) async {
    final dto = await _api.listCaseSources(caseId);
    return dto.items.map(CaseSourceUsage.fromDto).toList();
  }

  Future<void> addCaseSource(
    String caseId, {
    required String sourceRecordId,
    required String sourceVersionId,
    String? sourceParagraphId,
    String reason = '',
  }) {
    return _api.addCaseSource(
      caseId,
      sourceRecordId: sourceRecordId,
      sourceVersionId: sourceVersionId,
      sourceParagraphId: sourceParagraphId,
      reason: reason,
    );
  }

  Future<void> removeCaseSource(String caseId, String usageId) {
    return _api.removeCaseSource(caseId, usageId);
  }

  Future<List<OfficialTrackingItem>> officialTracking() async {
    final dto = await _api.officialTracking();
    return dto.items.map(OfficialTrackingItem.fromDto).toList();
  }
}
