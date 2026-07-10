import '../domain/case_memory.dart';
import 'case_memory_api.dart';

/// Domain operations over a case's structured memory.
class CaseMemoryRepository {
  const CaseMemoryRepository(this._api);

  final CaseMemoryApi _api;

  Future<CaseMemory> loadMemory(String caseId) async {
    return CaseMemory.fromDto(await _api.getMemory(caseId));
  }

  Future<void> confirmFact(String caseId, String factId) {
    return _api.confirmFact(caseId, factId);
  }

  Future<void> rejectFact(String caseId, String factId) {
    return _api.rejectFact(caseId, factId);
  }

  Future<void> updateFactValue(
    String caseId,
    String factId, {
    required int version,
    required String value,
  }) {
    return _api.updateFact(caseId, factId, version: version, value: value);
  }

  Future<void> resolveContradiction(
    String caseId,
    String contradictionId, {
    required String resolutionFactId,
    String note = '',
  }) {
    return _api.resolveContradiction(
      caseId,
      contradictionId,
      resolutionFactId: resolutionFactId,
      note: note,
    );
  }

  Future<void> resolveMissing(String caseId, String itemId) {
    return _api.resolveMissing(caseId, itemId);
  }
}
