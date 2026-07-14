import '../../../core/network/api_client.dart';

class SearchApi {
  const SearchApi(this._client);

  final ApiClient _client;

  static const String _searchLegalPath = '/api/v1/search/legal';
  static const String _searchSimilarPath = '/api/v1/search/similar';
  static const String _searchOpposingPath = '/api/v1/search/opposing';
  static const String _suggestionsPath = '/api/v1/search/suggestions';

  String _feedbackPath(String resultId) =>
      '/api/v1/search/results/$resultId/feedback';

  Future<Map<String, dynamic>> searchLegal({
    required String query,
    String? caseId,
    bool? officialOnly,
    List<String>? sourceTypes,
    String? court,
    int? limit,
    String? cursor,
    Object? cancelToken,
  }) async {
    final Map<String, dynamic> body = <String, dynamic>{'query': query};
    if (caseId != null) body['case_id'] = caseId;
    if (officialOnly != null) body['official_only'] = officialOnly;
    if (sourceTypes != null) body['source_types'] = sourceTypes;
    if (court != null) body['court'] = court;
    if (limit != null) body['limit'] = limit;
    if (cursor != null) body['cursor'] = cursor;

    return _client.postJson<Map<String, dynamic>>(
      _searchLegalPath,
      body: body,
      cancelToken: cancelToken,
    );
  }

  Future<Map<String, dynamic>> searchSimilar({
    required String sourceId,
    String? sourceParagraphId,
    int? limit,
    Object? cancelToken,
  }) async {
    final Map<String, dynamic> body = <String, dynamic>{'source_id': sourceId};
    if (sourceParagraphId != null) {
      body['source_paragraph_id'] = sourceParagraphId;
    }
    if (limit != null) body['limit'] = limit;

    return _client.postJson<Map<String, dynamic>>(
      _searchSimilarPath,
      body: body,
      cancelToken: cancelToken,
    );
  }

  Future<Map<String, dynamic>> searchOpposing({
    required String sourceId,
    Object? cancelToken,
  }) async {
    return _client.postJson<Map<String, dynamic>>(
      _searchOpposingPath,
      body: <String, dynamic>{'source_id': sourceId},
      cancelToken: cancelToken,
    );
  }

  Future<List<dynamic>> getSuggestions(
    String prefix, {
    Object? cancelToken,
  }) async {
    return _client.getJson<List<dynamic>>(
      _suggestionsPath,
      queryParameters: <String, dynamic>{'q': prefix},
      cancelToken: cancelToken,
    );
  }

  Future<void> submitFeedback(
    String resultId,
    String feedbackType, {
    Object? cancelToken,
  }) async {
    await _client.postJson<Map<String, dynamic>>(
      _feedbackPath(resultId),
      body: <String, dynamic>{'feedback_type': feedbackType},
      cancelToken: cancelToken,
    );
  }
}
