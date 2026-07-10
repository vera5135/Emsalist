import '../domain/case_item.dart';
import '../domain/chat_message.dart';
import 'case_api.dart';
import 'models/case_dto.dart';
import 'models/conversation_dto.dart';
import 'models/message_dto.dart';

/// A page of chat messages plus whether older/more exist.
class MessagePage {
  const MessagePage({
    required this.messages,
    required this.total,
    required this.hasMore,
    required this.offset,
  });

  final List<ChatMessage> messages;
  final int total;
  final bool hasMore;
  final int offset;
}

/// Domain operations over cases, conversations and messages.
class CaseRepository {
  const CaseRepository(this._api);

  final CaseApi _api;

  Future<List<CaseItem>> listCases({
    bool archived = false,
    int limit = 50,
    int offset = 0,
  }) async {
    final CaseListDto dto = await _api.listCases(
      archived: archived,
      limit: limit,
      offset: offset,
    );
    return dto.items.map(CaseItem.fromDto).toList();
  }

  Future<CaseItem> getCase(String caseId) async {
    return CaseItem.fromDto(await _api.getCase(caseId));
  }

  Future<CaseItem> createCase({
    String? title,
    String legalTopic = '',
    String initialNarrative = '',
  }) async {
    final CaseDto dto = await _api.createCase(
      title: title,
      legalTopic: legalTopic,
      initialNarrative: initialNarrative,
    );
    return CaseItem.fromDto(dto);
  }

  Future<CaseItem> archiveCase(String caseId) async {
    return CaseItem.fromDto(await _api.archiveCase(caseId));
  }

  Future<CaseItem> restoreCase(String caseId) async {
    return CaseItem.fromDto(await _api.restoreCase(caseId));
  }

  /// Resolves (creating if needed) the conversation for a case.
  Future<String> conversationIdForCase(String caseId) async {
    final ConversationDto dto = await _api.createOrGetConversation(caseId);
    return dto.id;
  }

  Future<MessagePage> loadMessages(
    String conversationId, {
    int limit = 30,
    int offset = 0,
  }) async {
    final MessageListDto dto = await _api.listMessages(
      conversationId,
      limit: limit,
      offset: offset,
    );
    return MessagePage(
      messages: dto.items.map(ChatMessage.fromDto).toList(),
      total: dto.total,
      hasMore: dto.hasMore,
      offset: dto.offset,
    );
  }

  Future<ChatMessage> sendMessage(
    String conversationId, {
    required String content,
    required String clientRequestId,
  }) async {
    final MessageDto dto = await _api.sendMessage(
      conversationId,
      content: content,
      clientRequestId: clientRequestId,
    );
    return ChatMessage.fromDto(dto);
  }
}
