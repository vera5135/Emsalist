import 'package:json_annotation/json_annotation.dart';

part 'message_dto.g.dart';

/// Mirrors backend `MessageResponse`.
@JsonSerializable(createToJson: false)
class MessageDto {
  const MessageDto({
    required this.id,
    required this.conversationId,
    required this.caseId,
    this.role = 'user',
    this.content = '',
    this.status = 'completed',
    this.parentMessageId,
    this.clientRequestId = '',
    this.createdAt,
    this.completedAt,
  });

  final String id;

  @JsonKey(name: 'conversation_id')
  final String conversationId;

  @JsonKey(name: 'case_id')
  final String caseId;

  final String role;
  final String content;
  final String status;

  @JsonKey(name: 'parent_message_id')
  final String? parentMessageId;

  @JsonKey(name: 'client_request_id')
  final String clientRequestId;

  @JsonKey(name: 'created_at')
  final String? createdAt;

  @JsonKey(name: 'completed_at')
  final String? completedAt;

  factory MessageDto.fromJson(Map<String, dynamic> json) =>
      _$MessageDtoFromJson(json);
}

/// Mirrors backend `MessageListResponse`.
@JsonSerializable(createToJson: false)
class MessageListDto {
  const MessageListDto({
    this.items = const <MessageDto>[],
    this.total = 0,
    this.limit = 30,
    this.offset = 0,
    this.hasMore = false,
  });

  final List<MessageDto> items;
  final int total;
  final int limit;
  final int offset;

  @JsonKey(name: 'has_more')
  final bool hasMore;

  factory MessageListDto.fromJson(Map<String, dynamic> json) =>
      _$MessageListDtoFromJson(json);
}
