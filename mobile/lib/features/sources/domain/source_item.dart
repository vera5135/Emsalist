import '../data/models/source_dto.dart';

/// User-facing Turkish label for an internal verification status.
/// Internal snake_case is never shown directly to the user.
String verificationBadgeLabel(String status) {
  switch (status) {
    case 'verified_official':
      return 'Resmî kaynaktan doğrulandı';
    case 'verified_secondary':
      return 'İkincil kaynaklarla doğrulandı';
    case 'editor_verified':
      return 'Editör tarafından doğrulandı';
    case 'needs_review':
      return 'İnceleme gerekli';
    case 'conflicting':
      return 'Çelişkili kaynak';
    case 'outdated':
      return 'Eski sürüm';
    case 'superseded':
      return 'Yeni sürümü var';
    case 'repealed':
      return 'Yürürlükten kaldırıldı';
    case 'unavailable':
      return 'Kaynağa şu anda ulaşılamıyor';
    case 'quarantined':
      return 'Kullanıma kapalı';
    default:
      return 'Durum bilinmiyor';
  }
}

String temporalStatusLabel(String status) {
  switch (status) {
    case 'valid':
      return 'Yürürlükte';
    case 'not_yet_effective':
      return 'Henüz yürürlükte değil';
    case 'expired':
      return 'Süresi dolmuş';
    case 'repealed':
      return 'Yürürlükten kaldırıldı';
    case 'superseded':
      return 'Yeni sürümü var';
    default:
      return 'Belirsiz';
  }
}

class SourceRecordItem {
  const SourceRecordItem({
    required this.id,
    required this.sourceType,
    required this.title,
    required this.court,
    required this.chamber,
    required this.caseNumber,
    required this.decisionNumber,
    required this.decisionDate,
    required this.officialUrl,
    required this.verificationStatus,
    required this.temporalStatus,
    required this.currentVersionId,
  });

  final String id;
  final String sourceType;
  final String title;
  final String court;
  final String chamber;
  final String caseNumber;
  final String decisionNumber;
  final String decisionDate;
  final String officialUrl;
  final String verificationStatus;
  final String temporalStatus;
  final String? currentVersionId;

  bool get isOfficial => verificationStatus == 'verified_official';
  String get displayTitle => title.trim().isEmpty ? 'İsimsiz kaynak' : title;
  String get badge => verificationBadgeLabel(verificationStatus);

  factory SourceRecordItem.fromDto(SourceRecordDto dto) => SourceRecordItem(
    id: dto.id,
    sourceType: dto.sourceType,
    title: dto.title,
    court: dto.court,
    chamber: dto.chamber,
    caseNumber: dto.caseNumber,
    decisionNumber: dto.decisionNumber,
    decisionDate: dto.decisionDate,
    officialUrl: dto.officialUrl,
    verificationStatus: dto.verificationStatus,
    temporalStatus: dto.temporalStatus,
    currentVersionId: dto.currentVersionId,
  );
}

class SourceParagraphItem {
  const SourceParagraphItem({
    required this.id,
    required this.paragraphIndex,
    required this.text,
    required this.articleNumber,
    required this.page,
  });

  final String id;
  final int paragraphIndex;
  final String text;
  final String articleNumber;
  final int? page;

  factory SourceParagraphItem.fromDto(SourceParagraphDto dto) =>
      SourceParagraphItem(
        id: dto.id,
        paragraphIndex: dto.paragraphIndex,
        text: dto.text,
        articleNumber: dto.articleNumber,
        page: dto.page,
      );
}

class CaseSourceUsage {
  const CaseSourceUsage({
    required this.id,
    required this.sourceTitle,
    required this.sourceType,
    required this.court,
    required this.decisionDate,
    required this.reason,
    required this.verificationStatus,
    required this.temporalStatus,
    required this.selectedParagraph,
    required this.usedInFinalDraft,
    required this.officialUrl,
    required this.sourceRecordId,
    required this.sourceVersionId,
    this.sourceParagraphId,
  });

  final String id;
  final String sourceTitle;
  final String sourceType;
  final String court;
  final String decisionDate;
  final String reason;
  final String verificationStatus;
  final String temporalStatus;
  final String selectedParagraph;
  final bool usedInFinalDraft;
  final String officialUrl;
  final String sourceRecordId;
  final String sourceVersionId;
  final String? sourceParagraphId;

  String get badge => verificationBadgeLabel(verificationStatus);
  String get displayTitle =>
      sourceTitle.trim().isEmpty ? 'İsimsiz kaynak' : sourceTitle;

  factory CaseSourceUsage.fromDto(SourceUsageDto dto) => CaseSourceUsage(
    id: dto.id,
    sourceTitle: dto.sourceTitle,
    sourceType: dto.sourceType,
    court: dto.court,
    decisionDate: dto.decisionDate,
    reason: dto.reason,
    verificationStatus: dto.verificationStatus,
    temporalStatus: dto.temporalStatus,
    selectedParagraph: dto.selectedParagraph,
    usedInFinalDraft: dto.usedInFinalDraft,
    officialUrl: dto.officialUrl,
    sourceRecordId: dto.sourceRecordId,
    sourceVersionId: dto.sourceVersionId,
    sourceParagraphId: dto.sourceParagraphId,
  );
}

class OfficialTrackingItem {
  const OfficialTrackingItem({
    required this.sourceId,
    required this.title,
    required this.sourceType,
    required this.lastCheckedAt,
    required this.temporalStatus,
    required this.verificationStatus,
    required this.newVersionDetected,
    required this.changeSummary,
    required this.affectedCaseCount,
    required this.requiresReview,
  });

  final String sourceId;
  final String title;
  final String sourceType;
  final String? lastCheckedAt;
  final String temporalStatus;
  final String verificationStatus;
  final bool newVersionDetected;
  final String? changeSummary;
  final int affectedCaseCount;
  final bool requiresReview;

  String get displayTitle => title.trim().isEmpty ? 'İsimsiz kaynak' : title;

  factory OfficialTrackingItem.fromDto(OfficialTrackingDto dto) =>
      OfficialTrackingItem(
        sourceId: dto.sourceId,
        title: dto.title,
        sourceType: dto.sourceType,
        lastCheckedAt: dto.lastSuccessfulCheckAt ?? dto.lastCheckedAt,
        temporalStatus: dto.temporalStatus,
        verificationStatus: dto.verificationStatus,
        newVersionDetected: dto.newVersionDetected,
        changeSummary: dto.changeSummary,
        affectedCaseCount: dto.affectedCaseCount,
        requiresReview: dto.requiresReview,
      );
}
