import '../../../core/network/api_client.dart';
import 'models/case_dto.dart';
import 'models/conversation_dto.dart';
import 'models/message_dto.dart';

/// Thin data source for the P2.3 case & conversation/message endpoints.
///
/// Uses the authenticated [ApiClient] so the Bearer token is attached and 401s
/// trigger refresh rotation. Message content is passed straight through; it is
/// never logged here.
class CaseApi {
  const CaseApi(this._client);

  final ApiClient _client;

  static const String casesPath = '/api/v1/cases';

  Future<CaseListDto> listCases({
    bool archived = false,
    int limit = 20,
    int offset = 0,
    Object? cancelToken,
  }) async {
    final Map<String, dynamic> json = await _client
        .getJson<Map<String, dynamic>>(
          casesPath,
          queryParameters: <String, dynamic>{
            'archived': archived,
            'limit': limit,
            'offset': offset,
          },
          cancelToken: cancelToken,
        );
    return CaseListDto.fromJson(json);
  }

  Future<CaseDto> getCase(String caseId, {Object? cancelToken}) async {
    final Map<String, dynamic> json = await _client
        .getJson<Map<String, dynamic>>(
          '$casesPath/$caseId',
          cancelToken: cancelToken,
        );
    return CaseDto.fromJson(json);
  }

  Future<CaseDto> createCase({
    String? title,
    String legalTopic = '',
    String initialNarrative = '',
    Object? cancelToken,
  }) async {
    final Map<String, dynamic> json = await _client
        .postJson<Map<String, dynamic>>(
          casesPath,
          body: <String, dynamic>{
            'title': title,
            'legal_topic': legalTopic,
            'initial_narrative': initialNarrative,
          },
          cancelToken: cancelToken,
        );
    return CaseDto.fromJson(json);
  }

  Future<CaseDto> updateCase(
    String caseId, {
    String? title,
    String? legalTopic,
    Object? cancelToken,
  }) async {
    final Map<String, dynamic> body = <String, dynamic>{};
    if (title != null) body['title'] = title;
    if (legalTopic != null) body['legal_topic'] = legalTopic;
    final Map<String, dynamic> json = await _client
        .postJson<Map<String, dynamic>>(
          '$casesPath/$caseId',
          body: body,
          cancelToken: cancelToken,
        );
    return CaseDto.fromJson(json);
  }

  Future<CaseDto> archiveCase(String caseId, {Object? cancelToken}) async {
    final Map<String, dynamic> json = await _client
        .postJson<Map<String, dynamic>>(
          '$casesPath/$caseId/archive',
          cancelToken: cancelToken,
        );
    return CaseDto.fromJson(json);
  }

  Future<CaseDto> restoreCase(String caseId, {Object? cancelToken}) async {
    final Map<String, dynamic> json = await _client
        .postJson<Map<String, dynamic>>(
          '$casesPath/$caseId/restore',
          cancelToken: cancelToken,
        );
    return CaseDto.fromJson(json);
  }

  Future<ConversationDto> createOrGetConversation(
    String caseId, {
    Object? cancelToken,
  }) async {
    final Map<String, dynamic> json = await _client
        .postJson<Map<String, dynamic>>(
          '$casesPath/$caseId/conversations',
          cancelToken: cancelToken,
        );
    return ConversationDto.fromJson(json);
  }

  Future<MessageListDto> listMessages(
    String conversationId, {
    int limit = 30,
    int offset = 0,
    Object? cancelToken,
  }) async {
    final Map<String, dynamic> json = await _client
        .getJson<Map<String, dynamic>>(
          '/api/v1/conversations/$conversationId/messages',
          queryParameters: <String, dynamic>{'limit': limit, 'offset': offset},
          cancelToken: cancelToken,
        );
    return MessageListDto.fromJson(json);
  }

  Future<MessageDto> sendMessage(
    String conversationId, {
    required String content,
    required String clientRequestId,
    Object? cancelToken,
  }) async {
    final Map<String, dynamic> json = await _client
        .postJson<Map<String, dynamic>>(
          '/api/v1/conversations/$conversationId/messages',
          body: <String, dynamic>{
            'content': content,
            'client_request_id': clientRequestId,
          },
          cancelToken: cancelToken,
        );
    return MessageDto.fromJson(json);
  }
}
