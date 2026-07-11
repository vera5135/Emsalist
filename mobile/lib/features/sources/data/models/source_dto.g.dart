// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'source_dto.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

SourceRecordDto _$SourceRecordDtoFromJson(Map<String, dynamic> json) =>
    SourceRecordDto(
      id: json['id'] as String,
      sourceType: json['source_type'] as String? ?? '',
      title: json['title'] as String? ?? '',
      court: json['court'] as String? ?? '',
      chamber: json['chamber'] as String? ?? '',
      caseNumber: json['case_number'] as String? ?? '',
      decisionNumber: json['decision_number'] as String? ?? '',
      decisionDate: json['decision_date'] as String? ?? '',
      publicationDate: json['publication_date'] as String? ?? '',
      officialUrl: json['official_url'] as String? ?? '',
      verificationStatus:
          json['verification_status'] as String? ?? 'needs_review',
      temporalStatus: json['temporal_status'] as String? ?? 'unknown',
      currentVersionId: json['current_version_id'] as String?,
      version: (json['version'] as num?)?.toInt() ?? 1,
    );

SourceRecordListDto _$SourceRecordListDtoFromJson(Map<String, dynamic> json) =>
    SourceRecordListDto(
      items:
          (json['items'] as List<dynamic>?)
              ?.map((e) => SourceRecordDto.fromJson(e as Map<String, dynamic>))
              .toList() ??
          const <SourceRecordDto>[],
      total: (json['total'] as num?)?.toInt() ?? 0,
      hasMore: json['has_more'] as bool? ?? false,
    );

SourceParagraphDto _$SourceParagraphDtoFromJson(Map<String, dynamic> json) =>
    SourceParagraphDto(
      id: json['id'] as String,
      paragraphIndex: (json['paragraph_index'] as num?)?.toInt() ?? 0,
      headingPath: json['heading_path'] as String? ?? '',
      text: json['text'] as String? ?? '',
      page: (json['page'] as num?)?.toInt(),
      articleNumber: json['article_number'] as String? ?? '',
    );

SourceUsageDto _$SourceUsageDtoFromJson(Map<String, dynamic> json) =>
    SourceUsageDto(
      id: json['id'] as String,
      caseId: json['case_id'] as String,
      sourceRecordId: json['source_record_id'] as String? ?? '',
      sourceVersionId: json['source_version_id'] as String? ?? '',
      sourceParagraphId: json['source_paragraph_id'] as String?,
      usageType: json['usage_type'] as String? ?? 'reference',
      reason: json['reason'] as String? ?? '',
      usedInFinalDraft: json['used_in_final_draft'] as bool? ?? false,
      sourceTitle: json['source_title'] as String? ?? '',
      sourceType: json['source_type'] as String? ?? '',
      court: json['court'] as String? ?? '',
      decisionDate: json['decision_date'] as String? ?? '',
      caseNumber: json['case_number'] as String? ?? '',
      decisionNumber: json['decision_number'] as String? ?? '',
      verificationStatus: json['verification_status'] as String? ?? '',
      temporalStatus: json['temporal_status'] as String? ?? '',
      officialUrl: json['official_url'] as String? ?? '',
      selectedParagraph: json['selected_paragraph'] as String? ?? '',
    );

SourceUsageListDto _$SourceUsageListDtoFromJson(Map<String, dynamic> json) =>
    SourceUsageListDto(
      items:
          (json['items'] as List<dynamic>?)
              ?.map((e) => SourceUsageDto.fromJson(e as Map<String, dynamic>))
              .toList() ??
          const <SourceUsageDto>[],
    );

OfficialTrackingDto _$OfficialTrackingDtoFromJson(Map<String, dynamic> json) =>
    OfficialTrackingDto(
      sourceId: json['source_id'] as String,
      title: json['title'] as String? ?? '',
      sourceType: json['source_type'] as String? ?? '',
      lastCheckedAt: json['last_checked_at'] as String?,
      lastSuccessfulCheckAt: json['last_successful_check_at'] as String?,
      temporalStatus: json['temporal_status'] as String? ?? '',
      verificationStatus: json['verification_status'] as String? ?? '',
      newVersionDetected: json['new_version_detected'] as bool? ?? false,
      changeSummary: json['change_summary'] as String?,
      affectedCaseCount: (json['affected_case_count'] as num?)?.toInt() ?? 0,
      affectedDraftSupported:
          json['affected_draft_supported'] as bool? ?? false,
      requiresReview: json['requires_review'] as bool? ?? false,
    );

OfficialTrackingListDto _$OfficialTrackingListDtoFromJson(
  Map<String, dynamic> json,
) => OfficialTrackingListDto(
  items:
      (json['items'] as List<dynamic>?)
          ?.map((e) => OfficialTrackingDto.fromJson(e as Map<String, dynamic>))
          .toList() ??
      const <OfficialTrackingDto>[],
);
