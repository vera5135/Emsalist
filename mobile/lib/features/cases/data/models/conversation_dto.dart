import 'package:json_annotation/json_annotation.dart';

part 'conversation_dto.g.dart';

/// Mirrors backend `ConversationResponse`.
@JsonSerializable(createToJson: false)
class ConversationDto {
  const ConversationDto({
    required this.id,
    required this.caseId,
    this.title = '',
    this.status = 'active',
    this.createdAt,
  });

  final String id;

  @JsonKey(name: 'case_id')
  final String caseId;

  final String title;
  final String status;

  @JsonKey(name: 'created_at')
  final String? createdAt;

  factory ConversationDto.fromJson(Map<String, dynamic> json) =>
      _$ConversationDtoFromJson(json);
}
