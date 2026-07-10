import 'package:json_annotation/json_annotation.dart';

part 'case_dto.g.dart';

/// Mirrors backend `CaseResponse`.
@JsonSerializable(createToJson: false)
class CaseDto {
  const CaseDto({
    required this.id,
    this.title = '',
    this.legalTopic = '',
    this.status = 'active',
    this.version = 1,
    this.createdAt,
    this.updatedAt,
    this.archivedAt,
  });

  final String id;
  final String title;

  @JsonKey(name: 'legal_topic')
  final String legalTopic;

  final String status;
  final int version;

  @JsonKey(name: 'created_at')
  final String? createdAt;

  @JsonKey(name: 'updated_at')
  final String? updatedAt;

  @JsonKey(name: 'archived_at')
  final String? archivedAt;

  factory CaseDto.fromJson(Map<String, dynamic> json) => _$CaseDtoFromJson(json);
}

/// Mirrors backend `CaseListResponse`.
@JsonSerializable(createToJson: false)
class CaseListDto {
  const CaseListDto({
    this.items = const <CaseDto>[],
    this.total = 0,
    this.limit = 20,
    this.offset = 0,
    this.hasMore = false,
  });

  final List<CaseDto> items;
  final int total;
  final int limit;
  final int offset;

  @JsonKey(name: 'has_more')
  final bool hasMore;

  factory CaseListDto.fromJson(Map<String, dynamic> json) =>
      _$CaseListDtoFromJson(json);
}
