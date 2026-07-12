import 'package:json_annotation/json_annotation.dart';

part 'source_dto.g.dart';

@JsonSerializable(createToJson: false)
class SourceRecordDto {
  const SourceRecordDto({
    required this.id,
    this.sourceType = '',
    this.title = '',
    this.court = '',
    this.chamber = '',
    this.caseNumber = '',
    this.decisionNumber = '',
    this.decisionDate = '',
    this.publicationDate = '',
    this.officialUrl = '',
    this.verificationStatus = 'needs_review',
    this.temporalStatus = 'unknown',
    this.currentVersionId,
    this.version = 1,
  });

  final String id;

  @JsonKey(name: 'source_type')
  final String sourceType;

  final String title;
  final String court;
  final String chamber;

  @JsonKey(name: 'case_number')
  final String caseNumber;

  @JsonKey(name: 'decision_number')
  final String decisionNumber;

  @JsonKey(name: 'decision_date')
  final String decisionDate;

  @JsonKey(name: 'publication_date')
  final String publicationDate;

  @JsonKey(name: 'official_url')
  final String officialUrl;

  @JsonKey(name: 'verification_status')
  final String verificationStatus;

  @JsonKey(name: 'temporal_status')
  final String temporalStatus;

  @JsonKey(name: 'current_version_id')
  final String? currentVersionId;

  final int version;

  factory SourceRecordDto.fromJson(Map<String, dynamic> json) =>
      _$SourceRecordDtoFromJson(json);
}

@JsonSerializable(createToJson: false)
class SourceRecordListDto {
  const SourceRecordListDto({
    this.items = const <SourceRecordDto>[],
    this.total = 0,
    this.hasMore = false,
  });

  final List<SourceRecordDto> items;
  final int total;

  @JsonKey(name: 'has_more')
  final bool hasMore;

  factory SourceRecordListDto.fromJson(Map<String, dynamic> json) =>
      _$SourceRecordListDtoFromJson(json);
}

@JsonSerializable(createToJson: false)
class SourceParagraphDto {
  const SourceParagraphDto({
    required this.id,
    this.paragraphIndex = 0,
    this.headingPath = '',
    this.text = '',
    this.page,
    this.articleNumber = '',
  });

  final String id;

  @JsonKey(name: 'paragraph_index')
  final int paragraphIndex;

  @JsonKey(name: 'heading_path')
  final String headingPath;

  final String text;
  final int? page;

  @JsonKey(name: 'article_number')
  final String articleNumber;

  factory SourceParagraphDto.fromJson(Map<String, dynamic> json) =>
      _$SourceParagraphDtoFromJson(json);
}

@JsonSerializable(createToJson: false)
class SourceUsageDto {
  const SourceUsageDto({
    required this.id,
    required this.caseId,
    this.sourceRecordId = '',
    this.sourceVersionId = '',
    this.sourceParagraphId,
    this.usageType = 'reference',
    this.reason = '',
    this.usedInFinalDraft = false,
    this.sourceTitle = '',
    this.sourceType = '',
    this.court = '',
    this.decisionDate = '',
    this.caseNumber = '',
    this.decisionNumber = '',
    this.verificationStatus = '',
    this.temporalStatus = '',
    this.officialUrl = '',
    this.selectedParagraph = '',
  });

  final String id;

  @JsonKey(name: 'case_id')
  final String caseId;

  @JsonKey(name: 'source_record_id')
  final String sourceRecordId;

  @JsonKey(name: 'source_version_id')
  final String sourceVersionId;

  @JsonKey(name: 'source_paragraph_id')
  final String? sourceParagraphId;

  @JsonKey(name: 'usage_type')
  final String usageType;

  final String reason;

  @JsonKey(name: 'used_in_final_draft')
  final bool usedInFinalDraft;

  @JsonKey(name: 'source_title')
  final String sourceTitle;

  @JsonKey(name: 'source_type')
  final String sourceType;

  final String court;

  @JsonKey(name: 'decision_date')
  final String decisionDate;

  @JsonKey(name: 'case_number')
  final String caseNumber;

  @JsonKey(name: 'decision_number')
  final String decisionNumber;

  @JsonKey(name: 'verification_status')
  final String verificationStatus;

  @JsonKey(name: 'temporal_status')
  final String temporalStatus;

  @JsonKey(name: 'official_url')
  final String officialUrl;

  @JsonKey(name: 'selected_paragraph')
  final String selectedParagraph;

  factory SourceUsageDto.fromJson(Map<String, dynamic> json) =>
      _$SourceUsageDtoFromJson(json);
}

@JsonSerializable(createToJson: false)
class SourceUsageListDto {
  const SourceUsageListDto({this.items = const <SourceUsageDto>[]});

  final List<SourceUsageDto> items;

  factory SourceUsageListDto.fromJson(Map<String, dynamic> json) =>
      _$SourceUsageListDtoFromJson(json);
}

@JsonSerializable(createToJson: false)
class OfficialTrackingDto {
  const OfficialTrackingDto({
    required this.sourceId,
    this.title = '',
    this.sourceType = '',
    this.lastCheckedAt,
    this.lastSuccessfulCheckAt,
    this.temporalStatus = '',
    this.verificationStatus = '',
    this.newVersionDetected = false,
    this.changeSummary,
    this.affectedCaseCount = 0,
    this.affectedDraftSupported = false,
    this.requiresReview = false,
  });

  @JsonKey(name: 'source_id')
  final String sourceId;

  final String title;

  @JsonKey(name: 'source_type')
  final String sourceType;

  @JsonKey(name: 'last_checked_at')
  final String? lastCheckedAt;

  @JsonKey(name: 'last_successful_check_at')
  final String? lastSuccessfulCheckAt;

  @JsonKey(name: 'temporal_status')
  final String temporalStatus;

  @JsonKey(name: 'verification_status')
  final String verificationStatus;

  @JsonKey(name: 'new_version_detected')
  final bool newVersionDetected;

  @JsonKey(name: 'change_summary')
  final String? changeSummary;

  @JsonKey(name: 'affected_case_count')
  final int affectedCaseCount;

  @JsonKey(name: 'affected_draft_supported')
  final bool affectedDraftSupported;

  @JsonKey(name: 'requires_review')
  final bool requiresReview;

  factory OfficialTrackingDto.fromJson(Map<String, dynamic> json) =>
      _$OfficialTrackingDtoFromJson(json);
}

@JsonSerializable(createToJson: false)
class OfficialTrackingListDto {
  const OfficialTrackingListDto({this.items = const <OfficialTrackingDto>[]});

  final List<OfficialTrackingDto> items;

  factory OfficialTrackingListDto.fromJson(Map<String, dynamic> json) =>
      _$OfficialTrackingListDtoFromJson(json);
}
