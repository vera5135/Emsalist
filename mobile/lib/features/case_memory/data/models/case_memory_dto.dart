import 'package:json_annotation/json_annotation.dart';

part 'case_memory_dto.g.dart';

@JsonSerializable(createToJson: false)
class FactDto {
  const FactDto({
    required this.id,
    required this.caseId,
    this.factType = '',
    this.value = '',
    this.importance = 'medium',
    this.sourceType = '',
    this.verificationStatus = 'suggested',
    this.version = 1,
  });

  final String id;

  @JsonKey(name: 'case_id')
  final String caseId;

  @JsonKey(name: 'fact_type')
  final String factType;

  final String value;
  final String importance;

  @JsonKey(name: 'source_type')
  final String sourceType;

  @JsonKey(name: 'verification_status')
  final String verificationStatus;

  final int version;

  factory FactDto.fromJson(Map<String, dynamic> json) =>
      _$FactDtoFromJson(json);
}

@JsonSerializable(createToJson: false)
class TimelineEventDto {
  const TimelineEventDto({
    required this.id,
    required this.caseId,
    this.eventType = '',
    this.description = '',
    this.eventDate = '',
    this.isApproximate = false,
    this.verificationStatus = 'suggested',
  });

  final String id;

  @JsonKey(name: 'case_id')
  final String caseId;

  @JsonKey(name: 'event_type')
  final String eventType;

  final String description;

  @JsonKey(name: 'event_date')
  final String eventDate;

  @JsonKey(name: 'is_approximate')
  final bool isApproximate;

  @JsonKey(name: 'verification_status')
  final String verificationStatus;

  factory TimelineEventDto.fromJson(Map<String, dynamic> json) =>
      _$TimelineEventDtoFromJson(json);
}

@JsonSerializable(createToJson: false)
class MissingInfoDto {
  const MissingInfoDto({
    required this.id,
    required this.caseId,
    this.fieldKey = '',
    this.label = '',
    this.importance = 'medium',
    this.status = 'open',
  });

  final String id;

  @JsonKey(name: 'case_id')
  final String caseId;

  @JsonKey(name: 'field_key')
  final String fieldKey;

  final String label;
  final String importance;
  final String status;

  factory MissingInfoDto.fromJson(Map<String, dynamic> json) =>
      _$MissingInfoDtoFromJson(json);
}

@JsonSerializable(createToJson: false)
class ContradictionDto {
  const ContradictionDto({
    required this.id,
    required this.caseId,
    this.contradictionType = '',
    this.description = '',
    this.factIds = const <String>[],
    this.severity = 'medium',
    this.status = 'open',
  });

  final String id;

  @JsonKey(name: 'case_id')
  final String caseId;

  @JsonKey(name: 'contradiction_type')
  final String contradictionType;

  final String description;

  @JsonKey(name: 'fact_ids')
  final List<String> factIds;

  final String severity;
  final String status;

  factory ContradictionDto.fromJson(Map<String, dynamic> json) =>
      _$ContradictionDtoFromJson(json);
}

@JsonSerializable(createToJson: false)
class RiskDto {
  const RiskDto({
    required this.id,
    required this.caseId,
    this.riskType = '',
    this.severity = 'low',
    this.title = '',
    this.rationale = '',
    this.mitigation = '',
    this.status = 'open',
  });

  final String id;

  @JsonKey(name: 'case_id')
  final String caseId;

  @JsonKey(name: 'risk_type')
  final String riskType;

  final String severity;
  final String title;
  final String rationale;
  final String mitigation;
  final String status;

  factory RiskDto.fromJson(Map<String, dynamic> json) =>
      _$RiskDtoFromJson(json);
}

@JsonSerializable(createToJson: false)
class CaseMemoryDto {
  const CaseMemoryDto({
    required this.caseId,
    this.overallRiskLevel = 'low',
    this.facts = const <FactDto>[],
    this.timeline = const <TimelineEventDto>[],
    this.missingInformation = const <MissingInfoDto>[],
    this.contradictions = const <ContradictionDto>[],
    this.risks = const <RiskDto>[],
  });

  @JsonKey(name: 'case_id')
  final String caseId;

  @JsonKey(name: 'overall_risk_level')
  final String overallRiskLevel;

  final List<FactDto> facts;
  final List<TimelineEventDto> timeline;

  @JsonKey(name: 'missing_information')
  final List<MissingInfoDto> missingInformation;

  final List<ContradictionDto> contradictions;
  final List<RiskDto> risks;

  factory CaseMemoryDto.fromJson(Map<String, dynamic> json) =>
      _$CaseMemoryDtoFromJson(json);
}
