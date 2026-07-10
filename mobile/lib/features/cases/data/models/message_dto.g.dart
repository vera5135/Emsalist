// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'message_dto.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

MessageDto _$MessageDtoFromJson(Map<String, dynamic> json) => MessageDto(
  id: json['id'] as String,
  conversationId: json['conversation_id'] as String,
  caseId: json['case_id'] as String,
  role: json['role'] as String? ?? 'user',
  content: json['content'] as String? ?? '',
  status: json['status'] as String? ?? 'completed',
  parentMessageId: json['parent_message_id'] as String?,
  clientRequestId: json['client_request_id'] as String? ?? '',
  createdAt: json['created_at'] as String?,
  completedAt: json['completed_at'] as String?,
);

MessageListDto _$MessageListDtoFromJson(Map<String, dynamic> json) =>
    MessageListDto(
      items:
          (json['items'] as List<dynamic>?)
              ?.map((e) => MessageDto.fromJson(e as Map<String, dynamic>))
              .toList() ??
          const <MessageDto>[],
      total: (json['total'] as num?)?.toInt() ?? 0,
      limit: (json['limit'] as num?)?.toInt() ?? 30,
      offset: (json['offset'] as num?)?.toInt() ?? 0,
      hasMore: json['has_more'] as bool? ?? false,
    );
