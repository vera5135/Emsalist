// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'case_memory_dto.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

FactDto _$FactDtoFromJson(Map<String, dynamic> json) => FactDto(
  id: json['id'] as String,
  caseId: json['case_id'] as String,
  factType: json['fact_type'] as String? ?? '',
  value: json['value'] as String? ?? '',
  importance: json['importance'] as String? ?? 'medium',
  sourceType: json['source_type'] as String? ?? '',
  verificationStatus: json['verification_status'] as String? ?? 'suggested',
  version: (json['version'] as num?)?.toInt() ?? 1,
);

TimelineEventDto _$TimelineEventDtoFromJson(Map<String, dynamic> json) =>
    TimelineEventDto(
      id: json['id'] as String,
      caseId: json['case_id'] as String,
      eventType: json['event_type'] as String? ?? '',
      description: json['description'] as String? ?? '',
      eventDate: json['event_date'] as String? ?? '',
      isApproximate: json['is_approximate'] as bool? ?? false,
      verificationStatus: json['verification_status'] as String? ?? 'suggested',
    );

MissingInfoDto _$MissingInfoDtoFromJson(Map<String, dynamic> json) =>
    MissingInfoDto(
      id: json['id'] as String,
      caseId: json['case_id'] as String,
      fieldKey: json['field_key'] as String? ?? '',
      label: json['label'] as String? ?? '',
      importance: json['importance'] as String? ?? 'medium',
      status: json['status'] as String? ?? 'open',
    );

ContradictionDto _$ContradictionDtoFromJson(Map<String, dynamic> json) =>
    ContradictionDto(
      id: json['id'] as String,
      caseId: json['case_id'] as String,
      contradictionType: json['contradiction_type'] as String? ?? '',
      description: json['description'] as String? ?? '',
      factIds:
          (json['fact_ids'] as List<dynamic>?)
              ?.map((e) => e as String)
              .toList() ??
          const <String>[],
      severity: json['severity'] as String? ?? 'medium',
      status: json['status'] as String? ?? 'open',
    );

RiskDto _$RiskDtoFromJson(Map<String, dynamic> json) => RiskDto(
  id: json['id'] as String,
  caseId: json['case_id'] as String,
  riskType: json['risk_type'] as String? ?? '',
  severity: json['severity'] as String? ?? 'low',
  title: json['title'] as String? ?? '',
  rationale: json['rationale'] as String? ?? '',
  mitigation: json['mitigation'] as String? ?? '',
  status: json['status'] as String? ?? 'open',
);

CaseMemoryDto _$CaseMemoryDtoFromJson(Map<String, dynamic> json) =>
    CaseMemoryDto(
      caseId: json['case_id'] as String,
      overallRiskLevel: json['overall_risk_level'] as String? ?? 'low',
      facts:
          (json['facts'] as List<dynamic>?)
              ?.map((e) => FactDto.fromJson(e as Map<String, dynamic>))
              .toList() ??
          const <FactDto>[],
      timeline:
          (json['timeline'] as List<dynamic>?)
              ?.map((e) => TimelineEventDto.fromJson(e as Map<String, dynamic>))
              .toList() ??
          const <TimelineEventDto>[],
      missingInformation:
          (json['missing_information'] as List<dynamic>?)
              ?.map((e) => MissingInfoDto.fromJson(e as Map<String, dynamic>))
              .toList() ??
          const <MissingInfoDto>[],
      contradictions:
          (json['contradictions'] as List<dynamic>?)
              ?.map((e) => ContradictionDto.fromJson(e as Map<String, dynamic>))
              .toList() ??
          const <ContradictionDto>[],
      risks:
          (json['risks'] as List<dynamic>?)
              ?.map((e) => RiskDto.fromJson(e as Map<String, dynamic>))
              .toList() ??
          const <RiskDto>[],
    );
