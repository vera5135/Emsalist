import '../../../core/network/api_client.dart';
import 'models/case_memory_dto.dart';

/// Thin data source for the P2.4 case memory endpoints (authenticated client).
class CaseMemoryApi {
  const CaseMemoryApi(this._client);

  final ApiClient _client;

  String _base(String caseId) => '/api/v1/cases/$caseId/memory';

  Future<CaseMemoryDto> getMemory(String caseId, {Object? cancelToken}) async {
    final Map<String, dynamic> json = await _client
        .getJson<Map<String, dynamic>>(_base(caseId), cancelToken: cancelToken);
    return CaseMemoryDto.fromJson(json);
  }

  Future<FactDto> confirmFact(
    String caseId,
    String factId, {
    Object? cancelToken,
  }) async {
    final Map<String, dynamic> json = await _client
        .postJson<Map<String, dynamic>>(
          '${_base(caseId)}/facts/$factId/confirm',
          cancelToken: cancelToken,
        );
    return FactDto.fromJson(json);
  }

  Future<FactDto> rejectFact(
    String caseId,
    String factId, {
    Object? cancelToken,
  }) async {
    final Map<String, dynamic> json = await _client
        .postJson<Map<String, dynamic>>(
          '${_base(caseId)}/facts/$factId/reject',
          cancelToken: cancelToken,
        );
    return FactDto.fromJson(json);
  }

  Future<FactDto> updateFact(
    String caseId,
    String factId, {
    required int version,
    String? value,
    Object? cancelToken,
  }) async {
    final Map<String, dynamic> body = <String, dynamic>{'version': version};
    if (value != null) body['value'] = value;
    final Map<String, dynamic> json = await _client
        .postJson<Map<String, dynamic>>(
          '${_base(caseId)}/facts/$factId',
          body: body,
          cancelToken: cancelToken,
        );
    return FactDto.fromJson(json);
  }

  Future<ContradictionDto> resolveContradiction(
    String caseId,
    String contradictionId, {
    required String resolutionFactId,
    String note = '',
    Object? cancelToken,
  }) async {
    final Map<String, dynamic> json = await _client
        .postJson<Map<String, dynamic>>(
          '${_base(caseId)}/contradictions/$contradictionId/resolve',
          body: <String, dynamic>{
            'resolution_fact_id': resolutionFactId,
            'note': note,
          },
          cancelToken: cancelToken,
        );
    return ContradictionDto.fromJson(json);
  }

  Future<MissingInfoDto> resolveMissing(
    String caseId,
    String itemId, {
    Object? cancelToken,
  }) async {
    final Map<String, dynamic> json = await _client
        .postJson<Map<String, dynamic>>(
          '${_base(caseId)}/missing-information/$itemId/resolve',
          cancelToken: cancelToken,
        );
    return MissingInfoDto.fromJson(json);
  }
}
