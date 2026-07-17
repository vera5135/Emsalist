import 'package:json_annotation/json_annotation.dart';

part 'draft_dto.g.dart';

@JsonSerializable(createToJson: false)
class DraftDto {
  const DraftDto({
    required this.id,
    required this.caseId,
    this.title = '',
    this.draftType = '',
    this.status = '',
    this.paragraphCount = 0,
    this.version = 1,
    this.createdAt = '',
    this.updatedAt = '',
    this.finalizedAt,
    this.supersedesDraftId,
  });

  final String id;

  @JsonKey(name: 'case_id')
  final String caseId;

  final String title;

  @JsonKey(name: 'draft_type')
  final String draftType;

  final String status;

  @JsonKey(name: 'paragraph_count')
  final int paragraphCount;

  final int version;

  @JsonKey(name: 'created_at')
  final String createdAt;

  @JsonKey(name: 'updated_at')
  final String updatedAt;

  @JsonKey(name: 'finalized_at')
  final String? finalizedAt;

  @JsonKey(name: 'supersedes_draft_id')
  final String? supersedesDraftId;

  factory DraftDto.fromJson(Map<String, dynamic> json) =>
      _$DraftDtoFromJson(json);
}

@JsonSerializable(createToJson: false)
class DraftListDto {
  const DraftListDto({this.items = const <DraftDto>[]});

  final List<DraftDto> items;

  factory DraftListDto.fromJson(Map<String, dynamic> json) =>
      _$DraftListDtoFromJson(json);
}

@JsonSerializable(createToJson: false)
class DraftDetailDto {
  const DraftDetailDto({
    required this.id,
    required this.caseId,
    this.title = '',
    this.draftType = '',
    this.status = '',
    this.paragraphCount = 0,
    this.version = 1,
    this.createdAt = '',
    this.updatedAt = '',
    this.finalizedAt,
    this.supersedesDraftId,
    this.paragraphs = const <DraftParagraphDto>[],
    this.issueLinks = const <DraftIssueLinkDto>[],
    this.sourceLinks = const <DraftSourceLinkDto>[],
  });

  final String id;

  @JsonKey(name: 'case_id')
  final String caseId;

  final String title;

  @JsonKey(name: 'draft_type')
  final String draftType;

  final String status;

  @JsonKey(name: 'paragraph_count')
  final int paragraphCount;

  final int version;

  @JsonKey(name: 'created_at')
  final String createdAt;

  @JsonKey(name: 'updated_at')
  final String updatedAt;

  @JsonKey(name: 'finalized_at')
  final String? finalizedAt;

  @JsonKey(name: 'supersedes_draft_id')
  final String? supersedesDraftId;

  final List<DraftParagraphDto> paragraphs;

  @JsonKey(name: 'issue_links')
  final List<DraftIssueLinkDto> issueLinks;

  @JsonKey(name: 'source_links')
  final List<DraftSourceLinkDto> sourceLinks;

  factory DraftDetailDto.fromJson(Map<String, dynamic> json) =>
      _$DraftDetailDtoFromJson(json);
}

@JsonSerializable(createToJson: false)
class DraftParagraphDto {
  const DraftParagraphDto({
    required this.id,
    required this.draftId,
    this.order = 0,
    this.paragraphType = '',
    this.text = '',
    this.version = 1,
    this.createdAt = '',
    this.updatedAt = '',
    this.verificationStatus = '',
    this.effectiveTrust,
    this.currentRevisionId,
    this.currentReviewId,
  });

  final String id;

  @JsonKey(name: 'draft_id')
  final String draftId;

  final int order;

  @JsonKey(name: 'paragraph_type')
  final String paragraphType;

  final String text;

  final int version;

  @JsonKey(name: 'created_at')
  final String createdAt;

  @JsonKey(name: 'updated_at')
  final String updatedAt;

  @JsonKey(name: 'verification_status')
  final String verificationStatus;

  @JsonKey(name: 'effective_trust')
  final double? effectiveTrust;

  @JsonKey(name: 'current_revision_id')
  final String? currentRevisionId;

  @JsonKey(name: 'current_review_id')
  final String? currentReviewId;

  factory DraftParagraphDto.fromJson(Map<String, dynamic> json) =>
      _$DraftParagraphDtoFromJson(json);
}

@JsonSerializable(createToJson: false)
class DraftIssueLinkDto {
  const DraftIssueLinkDto({
    required this.id,
    required this.draftParagraphId,
    required this.legalIssueId,
    this.relationType = '',
    this.createdAt = '',
    this.version = 1,
  });

  final String id;

  @JsonKey(name: 'draft_paragraph_id')
  final String draftParagraphId;

  @JsonKey(name: 'legal_issue_id')
  final String legalIssueId;

  @JsonKey(name: 'relation_type')
  final String relationType;

  @JsonKey(name: 'created_at')
  final String createdAt;

  final int version;

  factory DraftIssueLinkDto.fromJson(Map<String, dynamic> json) =>
      _$DraftIssueLinkDtoFromJson(json);
}

@JsonSerializable(createToJson: false)
class DraftSourceLinkDto {
  const DraftSourceLinkDto({
    required this.id,
    required this.draftParagraphId,
    required this.sourceRecordId,
    required this.sourceVersionId,
    this.sourceParagraphId,
    this.usageType = '',
    this.quoteHash = '',
    this.verificationStatus = '',
    this.effectiveTrust,
    this.createdAt = '',
    this.version = 1,
  });

  final String id;

  @JsonKey(name: 'draft_paragraph_id')
  final String draftParagraphId;

  @JsonKey(name: 'source_record_id')
  final String sourceRecordId;

  @JsonKey(name: 'source_version_id')
  final String sourceVersionId;

  @JsonKey(name: 'source_paragraph_id')
  final String? sourceParagraphId;

  @JsonKey(name: 'usage_type')
  final String usageType;

  @JsonKey(name: 'quote_hash')
  final String quoteHash;

  @JsonKey(name: 'verification_status')
  final String verificationStatus;

  @JsonKey(name: 'effective_trust')
  final double? effectiveTrust;

  @JsonKey(name: 'created_at')
  final String createdAt;

  final int version;

  factory DraftSourceLinkDto.fromJson(Map<String, dynamic> json) =>
      _$DraftSourceLinkDtoFromJson(json);
}

@JsonSerializable(createToJson: false)
class DraftRevisionDto {
  const DraftRevisionDto({
    required this.id,
    required this.draftParagraphId,
    required this.revisionNumber,
    required this.changeType,
    required this.createdBy,
    required this.createdAt,
    required this.textHash,
    required this.currentRevision,
    this.text = '',
  });

  final String id;

  @JsonKey(name: 'draft_paragraph_id')
  final String draftParagraphId;

  @JsonKey(name: 'revision_number')
  final int revisionNumber;

  @JsonKey(name: 'change_type')
  final String changeType;

  @JsonKey(name: 'created_by')
  final String createdBy;

  @JsonKey(name: 'created_at')
  final String createdAt;

  @JsonKey(name: 'text_hash')
  final String textHash;

  @JsonKey(name: 'current_revision')
  final bool currentRevision;

  final String text;

  factory DraftRevisionDto.fromJson(Map<String, dynamic> json) =>
      _$DraftRevisionDtoFromJson(json);
}

@JsonSerializable(createToJson: false)
class DraftReviewEventDto {
  const DraftReviewEventDto({
    required this.id,
    required this.draftParagraphId,
    required this.paragraphRevisionId,
    required this.decision,
    required this.reasonCode,
    required this.reviewerUserId,
    required this.paragraphVersion,
    required this.createdAt,
  });

  final String id;

  @JsonKey(name: 'draft_paragraph_id')
  final String draftParagraphId;

  @JsonKey(name: 'paragraph_revision_id')
  final String paragraphRevisionId;

  final String decision;

  @JsonKey(name: 'reason_code')
  final String reasonCode;

  @JsonKey(name: 'reviewer_user_id')
  final String reviewerUserId;

  @JsonKey(name: 'paragraph_version')
  final int paragraphVersion;

  @JsonKey(name: 'created_at')
  final String createdAt;

  factory DraftReviewEventDto.fromJson(Map<String, dynamic> json) =>
      _$DraftReviewEventDtoFromJson(json);
}

@JsonSerializable(createToJson: false)
class DraftReadinessDto {
  const DraftReadinessDto({
    this.status = '',
    this.blockedReasons = const <String>[],
    this.warnings = const <String>[],
    this.metrics = const <String, dynamic>{},
  });

  final String status;

  @JsonKey(name: 'blocked_reasons')
  final List<String> blockedReasons;

  final List<String> warnings;

  final Map<String, dynamic> metrics;

  factory DraftReadinessDto.fromJson(Map<String, dynamic> json) =>
      _$DraftReadinessDtoFromJson(json);
}

@JsonSerializable(createToJson: false)
class SectionPlanEntryDto {
  const SectionPlanEntryDto({
    this.sectionTitle = '',
    this.sectionType = '',
    this.recommendedParagraphs = 0,
    this.instructions = '',
  });

  @JsonKey(name: 'section_title')
  final String sectionTitle;

  @JsonKey(name: 'section_type')
  final String sectionType;

  @JsonKey(name: 'recommended_paragraphs')
  final int recommendedParagraphs;

  final String instructions;

  factory SectionPlanEntryDto.fromJson(Map<String, dynamic> json) =>
      _$SectionPlanEntryDtoFromJson(json);
}

@JsonSerializable(createToJson: false)
class DraftPlanDto {
  const DraftPlanDto({
    this.draftId = '',
    this.draftType = '',
    this.sections = const <SectionPlanEntryDto>[],
  });

  @JsonKey(name: 'draft_id')
  final String draftId;

  @JsonKey(name: 'draft_type')
  final String draftType;

  final List<SectionPlanEntryDto> sections;

  factory DraftPlanDto.fromJson(Map<String, dynamic> json) =>
      _$DraftPlanDtoFromJson(json);
}

@JsonSerializable(createToJson: false)
class DraftGenerateDto {
  const DraftGenerateDto({
    this.draftId = '',
    this.paragraphId = '',
    this.text = '',
    this.metadata = const <String, dynamic>{},
  });

  @JsonKey(name: 'draft_id')
  final String draftId;

  @JsonKey(name: 'paragraph_id')
  final String paragraphId;

  final String text;

  final Map<String, dynamic> metadata;

  factory DraftGenerateDto.fromJson(Map<String, dynamic> json) =>
      _$DraftGenerateDtoFromJson(json);
}

@JsonSerializable(createToJson: false)
class DraftValidationDto {
  const DraftValidationDto({
    this.valid = false,
    this.blockingErrors = const <String>[],
    this.warnings = const <String>[],
    this.metrics = const <String, dynamic>{},
  });

  final bool valid;

  @JsonKey(name: 'blocking_errors')
  final List<String> blockingErrors;

  final List<String> warnings;

  final Map<String, dynamic> metrics;

  factory DraftValidationDto.fromJson(Map<String, dynamic> json) =>
      _$DraftValidationDtoFromJson(json);
}

@JsonSerializable(createToJson: false)
class DraftFinalizeDto {
  const DraftFinalizeDto({
    required this.id,
    required this.caseId,
    this.status = '',
    this.finalizedAt = '',
    this.version = 1,
    this.paragraphCount = 0,
    this.issueLinkCount = 0,
    this.sourceLinkCount = 0,
    this.markedSourceUsageCount = 0,
  });

  final String id;

  @JsonKey(name: 'case_id')
  final String caseId;

  final String status;

  @JsonKey(name: 'finalized_at')
  final String finalizedAt;

  final int version;

  @JsonKey(name: 'paragraph_count')
  final int paragraphCount;

  @JsonKey(name: 'issue_link_count')
  final int issueLinkCount;

  @JsonKey(name: 'source_link_count')
  final int sourceLinkCount;

  @JsonKey(name: 'marked_source_usage_count')
  final int markedSourceUsageCount;

  factory DraftFinalizeDto.fromJson(Map<String, dynamic> json) =>
      _$DraftFinalizeDtoFromJson(json);
}

@JsonSerializable(createToJson: false)
class DraftGenerationJobDto {
  const DraftGenerationJobDto({
    required this.jobId,
    required this.draftId,
    this.status = '',
    this.stage = '',
    this.progressPercent = 0,
    this.requestedDraftVersion = 1,
    this.resultDraftVersion,
    this.providerName = '',
    this.modelName = '',
    this.safeErrorCode = '',
    this.safeMetrics = const <String, dynamic>{},
    this.queuedAt = '',
    this.startedAt,
    this.completedAt,
  });

  @JsonKey(name: 'job_id')
  final String jobId;

  @JsonKey(name: 'draft_id')
  final String draftId;

  final String status;

  final String stage;

  @JsonKey(name: 'progress_percent')
  final int progressPercent;

  @JsonKey(name: 'requested_draft_version')
  final int requestedDraftVersion;

  @JsonKey(name: 'result_draft_version')
  final int? resultDraftVersion;

  @JsonKey(name: 'provider_name')
  final String providerName;

  @JsonKey(name: 'model_name')
  final String modelName;

  @JsonKey(name: 'safe_error_code')
  final String safeErrorCode;

  @JsonKey(name: 'safe_metrics')
  final Map<String, dynamic> safeMetrics;

  @JsonKey(name: 'queued_at')
  final String queuedAt;

  @JsonKey(name: 'started_at')
  final String? startedAt;

  @JsonKey(name: 'completed_at')
  final String? completedAt;

  factory DraftGenerationJobDto.fromJson(Map<String, dynamic> json) =>
      _$DraftGenerationJobDtoFromJson(json);
}

@JsonSerializable(createToJson: false)
class DraftRevisionActionDto {
  const DraftRevisionActionDto({
    required this.paragraphId,
    this.draftVersion = 1,
    this.paragraphVersion = 1,
    this.revisionId = '',
  });

  @JsonKey(name: 'paragraph_id')
  final String paragraphId;

  @JsonKey(name: 'draft_version')
  final int draftVersion;

  @JsonKey(name: 'paragraph_version')
  final int paragraphVersion;

  @JsonKey(name: 'revision_id')
  final String revisionId;

  factory DraftRevisionActionDto.fromJson(Map<String, dynamic> json) =>
      _$DraftRevisionActionDtoFromJson(json);
}

@JsonSerializable(createToJson: false)
class DraftReviewActionDto {
  const DraftReviewActionDto({
    required this.paragraphId,
    this.draftVersion = 1,
    this.paragraphVersion = 1,
    this.revisionId = '',
  });

  @JsonKey(name: 'paragraph_id')
  final String paragraphId;

  @JsonKey(name: 'draft_version')
  final int draftVersion;

  @JsonKey(name: 'paragraph_version')
  final int paragraphVersion;

  @JsonKey(name: 'revision_id')
  final String revisionId;

  factory DraftReviewActionDto.fromJson(Map<String, dynamic> json) =>
      _$DraftReviewActionDtoFromJson(json);
}

@JsonSerializable(createToJson: true)
class DraftCreateRequestDto {
  const DraftCreateRequestDto({
    required this.title,
    required this.draftType,
    this.supersedesDraftId,
  });

  final String title;

  @JsonKey(name: 'draft_type')
  final String draftType;

  @JsonKey(name: 'supersedes_draft_id')
  final String? supersedesDraftId;

  Map<String, dynamic> toJson() => _$DraftCreateRequestDtoToJson(this);
}
