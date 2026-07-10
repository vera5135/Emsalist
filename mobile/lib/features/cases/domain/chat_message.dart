import '../data/models/message_dto.dart';

enum ChatMessageRole { user, assistant }

/// UI-facing delivery status of a chat message.
///
/// [sending]/[failed] are local-only states for optimistic user messages;
/// server-persisted messages are [sent].
enum ChatMessageStatus { sending, sent, failed }

/// Domain representation of a chat message shown in the conversation.
class ChatMessage {
  const ChatMessage({
    required this.id,
    required this.role,
    required this.content,
    required this.status,
    required this.clientRequestId,
    this.createdAt,
  });

  final String id;
  final ChatMessageRole role;
  final String content;
  final ChatMessageStatus status;
  final String clientRequestId;
  final DateTime? createdAt;

  bool get isUser => role == ChatMessageRole.user;
  bool get isFailed => status == ChatMessageStatus.failed;
  bool get isSending => status == ChatMessageStatus.sending;

  ChatMessage copyWith({
    String? id,
    ChatMessageStatus? status,
    DateTime? createdAt,
  }) {
    return ChatMessage(
      id: id ?? this.id,
      role: role,
      content: content,
      status: status ?? this.status,
      clientRequestId: clientRequestId,
      createdAt: createdAt ?? this.createdAt,
    );
  }

  factory ChatMessage.fromDto(MessageDto dto) {
    return ChatMessage(
      id: dto.id,
      role: dto.role == 'assistant'
          ? ChatMessageRole.assistant
          : ChatMessageRole.user,
      content: dto.content,
      status: ChatMessageStatus.sent,
      clientRequestId: dto.clientRequestId,
      createdAt: DateTime.tryParse(dto.createdAt ?? ''),
    );
  }
}
