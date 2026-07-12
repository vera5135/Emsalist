import '../../../core/network/api_client.dart';
import 'models/source_dto.dart';

/// Thin data source for the P2.6 legal source endpoints (authenticated client).
class SourceApi {
  const SourceApi(this._client);

  final ApiClient _client;

  static const String sourcesPath = '/api/v1/legal-sources';
  static const String trackingPath = '/api/v1/official-source-tracking';

  Future<SourceRecordListDto> listSources({
    String? sourceType,
    String? verificationStatus,
    int limit = 50,
    int offset = 0,
    Object? cancelToken,
  }) async {
    final Map<String, dynamic> query = <String, dynamic>{
      'limit': limit,
      'offset': offset,
    };
    if (sourceType != null) query['source_type'] = sourceType;
    if (verificationStatus != null) {
      query['verification_status'] = verificationStatus;
    }
    final Map<String, dynamic> json = await _client
        .getJson<Map<String, dynamic>>(
          sourcesPath,
          queryParameters: query,
          cancelToken: cancelToken,
        );
    return SourceRecordListDto.fromJson(json);
  }

  Future<SourceRecordDto> getSource(
    String sourceId, {
    Object? cancelToken,
  }) async {
    final Map<String, dynamic> json = await _client
        .getJson<Map<String, dynamic>>(
          '$sourcesPath/$sourceId',
          cancelToken: cancelToken,
        );
    return SourceRecordDto.fromJson(json);
  }

  Future<List<SourceParagraphDto>> listParagraphs(
    String sourceId, {
    Object? cancelToken,
  }) async {
    final List<dynamic> json = await _client.getJson<List<dynamic>>(
      '$sourcesPath/$sourceId/paragraphs',
      cancelToken: cancelToken,
    );
    return json
        .map(
          (dynamic e) => SourceParagraphDto.fromJson(e as Map<String, dynamic>),
        )
        .toList();
  }

  Future<OfficialTrackingListDto> officialTracking({
    Object? cancelToken,
  }) async {
    final Map<String, dynamic> json = await _client
        .getJson<Map<String, dynamic>>(trackingPath, cancelToken: cancelToken);
    return OfficialTrackingListDto.fromJson(json);
  }

  // --- Case source usage --------------------------------------------------
  String _caseBase(String caseId) => '/api/v1/cases/$caseId/sources';

  Future<SourceUsageListDto> listCaseSources(
    String caseId, {
    Object? cancelToken,
  }) async {
    final Map<String, dynamic> json = await _client
        .getJson<Map<String, dynamic>>(
          _caseBase(caseId),
          cancelToken: cancelToken,
        );
    return SourceUsageListDto.fromJson(json);
  }

  Future<SourceUsageDto> addCaseSource(
    String caseId, {
    required String sourceRecordId,
    required String sourceVersionId,
    String? sourceParagraphId,
    String reason = '',
  }) async {
    final Map<String, dynamic> json = await _client
        .postJson<Map<String, dynamic>>(
          _caseBase(caseId),
          body: <String, dynamic>{
            'source_record_id': sourceRecordId,
            'source_version_id': sourceVersionId,
            if (sourceParagraphId != null)
              'source_paragraph_id': sourceParagraphId,
            'reason': reason,
          },
        );
    return SourceUsageDto.fromJson(json);
  }

  Future<void> removeCaseSource(String caseId, String usageId) async {
    await _client.deleteJson<Map<String, dynamic>>(
      '${_caseBase(caseId)}/$usageId',
    );
  }
}
