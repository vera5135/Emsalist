// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'draft_dto.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

DraftDto _$DraftDtoFromJson(Map<String, dynamic> json) => DraftDto(
  id: json['id'] as String,
  caseId: json['case_id'] as String,
  title: json['title'] as String? ?? '',
  draftType: json['draft_type'] as String? ?? '',
  status: json['status'] as String? ?? '',
  paragraphCount: (json['paragraph_count'] as num?)?.toInt() ?? 0,
  version: (json['version'] as num?)?.toInt() ?? 1,
  createdAt: json['created_at'] as String? ?? '',
  updatedAt: json['updated_at'] as String? ?? '',
  finalizedAt: json['finalized_at'] as String?,
  supersedesDraftId: json['supersedes_draft_id'] as String?,
);

DraftListDto _$DraftListDtoFromJson(Map<String, dynamic> json) => DraftListDto(
  items:
      (json['items'] as List<dynamic>?)
          ?.map((e) => DraftDto.fromJson(e as Map<String, dynamic>))
          .toList() ??
      const <DraftDto>[],
);

DraftDetailDto _$DraftDetailDtoFromJson(
  Map<String, dynamic> json,
) => DraftDetailDto(
  id: json['id'] as String,
  caseId: json['case_id'] as String,
  title: json['title'] as String? ?? '',
  draftType: json['draft_type'] as String? ?? '',
  status: json['status'] as String? ?? '',
  paragraphCount: (json['paragraph_count'] as num?)?.toInt() ?? 0,
  version: (json['version'] as num?)?.toInt() ?? 1,
  createdAt: json['created_at'] as String? ?? '',
  updatedAt: json['updated_at'] as String? ?? '',
  finalizedAt: json['finalized_at'] as String?,
  supersedesDraftId: json['supersedes_draft_id'] as String?,
  paragraphs:
      (json['paragraphs'] as List<dynamic>?)
          ?.map((e) => DraftParagraphDto.fromJson(e as Map<String, dynamic>))
          .toList() ??
      const <DraftParagraphDto>[],
  issueLinks:
      (json['issue_links'] as List<dynamic>?)
          ?.map((e) => DraftIssueLinkDto.fromJson(e as Map<String, dynamic>))
          .toList() ??
      const <DraftIssueLinkDto>[],
  sourceLinks:
      (json['source_links'] as List<dynamic>?)
          ?.map((e) => DraftSourceLinkDto.fromJson(e as Map<String, dynamic>))
          .toList() ??
      const <DraftSourceLinkDto>[],
);

DraftParagraphDto _$DraftParagraphDtoFromJson(Map<String, dynamic> json) =>
    DraftParagraphDto(
      id: json['id'] as String,
      draftId: json['draft_id'] as String,
      order: (json['order'] as num?)?.toInt() ?? 0,
      paragraphType: json['paragraph_type'] as String? ?? '',
      text: json['text'] as String? ?? '',
      version: (json['version'] as num?)?.toInt() ?? 1,
      createdAt: json['created_at'] as String? ?? '',
      updatedAt: json['updated_at'] as String? ?? '',
      verificationStatus: json['verification_status'] as String? ?? '',
      effectiveTrust: (json['effective_trust'] as num?)?.toDouble(),
      currentRevisionId: json['current_revision_id'] as String?,
      currentReviewId: json['current_review_id'] as String?,
      generatedBy: json['generated_by'] as String?,
      modelName: json['model_name'] as String?,
    );

DraftIssueLinkDto _$DraftIssueLinkDtoFromJson(Map<String, dynamic> json) =>
    DraftIssueLinkDto(
      id: json['id'] as String,
      draftParagraphId: json['draft_paragraph_id'] as String,
      legalIssueId: json['legal_issue_id'] as String,
      relationType: json['relation_type'] as String? ?? '',
      createdAt: json['created_at'] as String? ?? '',
      version: (json['version'] as num?)?.toInt() ?? 1,
    );

DraftSourceLinkDto _$DraftSourceLinkDtoFromJson(Map<String, dynamic> json) =>
    DraftSourceLinkDto(
      id: json['id'] as String,
      draftParagraphId: json['draft_paragraph_id'] as String,
      sourceRecordId: json['source_record_id'] as String,
      sourceVersionId: json['source_version_id'] as String,
      sourceParagraphId: json['source_paragraph_id'] as String?,
      usageType: json['usage_type'] as String? ?? '',
      quoteHash: json['quote_hash'] as String? ?? '',
      verificationStatus: json['verification_status'] as String? ?? '',
      effectiveTrust: (json['effective_trust'] as num?)?.toDouble(),
      createdAt: json['created_at'] as String? ?? '',
      version: (json['version'] as num?)?.toInt() ?? 1,
    );

DraftRevisionDto _$DraftRevisionDtoFromJson(Map<String, dynamic> json) =>
    DraftRevisionDto(
      id: json['id'] as String,
      draftParagraphId: json['draft_paragraph_id'] as String,
      revisionNumber: (json['revision_number'] as num).toInt(),
      changeType: json['change_type'] as String,
      createdBy: json['created_by'] as String,
      createdAt: json['created_at'] as String,
      textHash: json['text_hash'] as String,
      currentRevision: json['current_revision'] as bool,
      text: json['text'] as String? ?? '',
    );

DraftReviewEventDto _$DraftReviewEventDtoFromJson(Map<String, dynamic> json) =>
    DraftReviewEventDto(
      id: json['id'] as String,
      draftParagraphId: json['draft_paragraph_id'] as String,
      paragraphRevisionId: json['paragraph_revision_id'] as String,
      decision: json['decision'] as String,
      reasonCode: json['reason_code'] as String,
      reviewerUserId: json['reviewer_user_id'] as String,
      paragraphVersion: (json['paragraph_version'] as num).toInt(),
      createdAt: json['created_at'] as String,
    );

DraftReadinessDto _$DraftReadinessDtoFromJson(Map<String, dynamic> json) =>
    DraftReadinessDto(
      status: json['status'] as String? ?? '',
      blockedReasons:
          (json['blocked_reasons'] as List<dynamic>?)
              ?.map((e) => e as String)
              .toList() ??
          const <String>[],
      warnings:
          (json['warnings'] as List<dynamic>?)
              ?.map((e) => e as String)
              .toList() ??
          const <String>[],
      metrics:
          json['metrics'] as Map<String, dynamic>? ?? const <String, dynamic>{},
    );

SectionPlanEntryDto _$SectionPlanEntryDtoFromJson(Map<String, dynamic> json) =>
    SectionPlanEntryDto(
      sectionTitle: json['section_title'] as String? ?? '',
      sectionType: json['section_type'] as String? ?? '',
      recommendedParagraphs:
          (json['recommended_paragraphs'] as num?)?.toInt() ?? 0,
      instructions: json['instructions'] as String? ?? '',
    );

DraftPlanDto _$DraftPlanDtoFromJson(Map<String, dynamic> json) => DraftPlanDto(
  draftId: json['draft_id'] as String? ?? '',
  draftType: json['draft_type'] as String? ?? '',
  sections:
      (json['sections'] as List<dynamic>?)
          ?.map((e) => SectionPlanEntryDto.fromJson(e as Map<String, dynamic>))
          .toList() ??
      const <SectionPlanEntryDto>[],
);

DraftGenerateDto _$DraftGenerateDtoFromJson(Map<String, dynamic> json) =>
    DraftGenerateDto(
      draftId: json['draft_id'] as String? ?? '',
      paragraphId: json['paragraph_id'] as String? ?? '',
      text: json['text'] as String? ?? '',
      metadata:
          json['metadata'] as Map<String, dynamic>? ??
          const <String, dynamic>{},
    );

DraftValidationDto _$DraftValidationDtoFromJson(Map<String, dynamic> json) =>
    DraftValidationDto(
      valid: json['valid'] as bool? ?? false,
      blockingErrors:
          (json['blocking_errors'] as List<dynamic>?)
              ?.map((e) => e as String)
              .toList() ??
          const <String>[],
      warnings:
          (json['warnings'] as List<dynamic>?)
              ?.map((e) => e as String)
              .toList() ??
          const <String>[],
      metrics:
          json['metrics'] as Map<String, dynamic>? ?? const <String, dynamic>{},
    );

DraftFinalizeDto _$DraftFinalizeDtoFromJson(Map<String, dynamic> json) =>
    DraftFinalizeDto(
      id: json['id'] as String,
      caseId: json['case_id'] as String,
      status: json['status'] as String? ?? '',
      finalizedAt: json['finalized_at'] as String? ?? '',
      version: (json['version'] as num?)?.toInt() ?? 1,
      paragraphCount: (json['paragraph_count'] as num?)?.toInt() ?? 0,
      issueLinkCount: (json['issue_link_count'] as num?)?.toInt() ?? 0,
      sourceLinkCount: (json['source_link_count'] as num?)?.toInt() ?? 0,
      markedSourceUsageCount:
          (json['marked_source_usage_count'] as num?)?.toInt() ?? 0,
    );

DraftGenerationJobDto _$DraftGenerationJobDtoFromJson(
  Map<String, dynamic> json,
) => DraftGenerationJobDto(
  jobId: json['job_id'] as String,
  draftId: json['draft_id'] as String,
  status: json['status'] as String? ?? '',
  stage: json['stage'] as String? ?? '',
  progressPercent: (json['progress_percent'] as num?)?.toInt() ?? 0,
  requestedDraftVersion:
      (json['requested_draft_version'] as num?)?.toInt() ?? 1,
  resultDraftVersion: (json['result_draft_version'] as num?)?.toInt(),
  providerName: json['provider_name'] as String? ?? '',
  modelName: json['model_name'] as String? ?? '',
  safeErrorCode: json['safe_error_code'] as String? ?? '',
  safeMetrics:
      json['safe_metrics'] as Map<String, dynamic>? ??
      const <String, dynamic>{},
  queuedAt: json['queued_at'] as String? ?? '',
  startedAt: json['started_at'] as String?,
  completedAt: json['completed_at'] as String?,
);

DraftRevisionActionDto _$DraftRevisionActionDtoFromJson(
  Map<String, dynamic> json,
) => DraftRevisionActionDto(
  paragraphId: json['paragraph_id'] as String,
  draftVersion: (json['draft_version'] as num?)?.toInt() ?? 1,
  paragraphVersion: (json['paragraph_version'] as num?)?.toInt() ?? 1,
  revisionId: json['revision_id'] as String? ?? '',
);

DraftReviewActionDto _$DraftReviewActionDtoFromJson(
  Map<String, dynamic> json,
) => DraftReviewActionDto(
  paragraphId: json['paragraph_id'] as String,
  draftVersion: (json['draft_version'] as num?)?.toInt() ?? 1,
  paragraphVersion: (json['paragraph_version'] as num?)?.toInt() ?? 1,
  revisionId: json['revision_id'] as String? ?? '',
);

DraftCreateRequestDto _$DraftCreateRequestDtoFromJson(
  Map<String, dynamic> json,
) => DraftCreateRequestDto(
  title: json['title'] as String,
  draftType: json['draft_type'] as String,
  supersedesDraftId: json['supersedes_draft_id'] as String?,
);

Map<String, dynamic> _$DraftCreateRequestDtoToJson(
  DraftCreateRequestDto instance,
) => <String, dynamic>{
  'title': instance.title,
  'draft_type': instance.draftType,
  'supersedes_draft_id': instance.supersedesDraftId,
};
