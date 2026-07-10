// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'case_dto.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

CaseDto _$CaseDtoFromJson(Map<String, dynamic> json) => CaseDto(
  id: json['id'] as String,
  title: json['title'] as String? ?? '',
  legalTopic: json['legal_topic'] as String? ?? '',
  status: json['status'] as String? ?? 'active',
  version: (json['version'] as num?)?.toInt() ?? 1,
  createdAt: json['created_at'] as String?,
  updatedAt: json['updated_at'] as String?,
  archivedAt: json['archived_at'] as String?,
);

CaseListDto _$CaseListDtoFromJson(Map<String, dynamic> json) => CaseListDto(
  items:
      (json['items'] as List<dynamic>?)
          ?.map((e) => CaseDto.fromJson(e as Map<String, dynamic>))
          .toList() ??
      const <CaseDto>[],
  total: (json['total'] as num?)?.toInt() ?? 0,
  limit: (json['limit'] as num?)?.toInt() ?? 20,
  offset: (json['offset'] as num?)?.toInt() ?? 0,
  hasMore: json['has_more'] as bool? ?? false,
);
