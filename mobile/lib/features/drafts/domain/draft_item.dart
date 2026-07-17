import '../data/models/draft_dto.dart';

String draftTypeLabel(String type) {
  switch (type) {
    case 'dava_dilekcesi':
      return 'Dava Dilekçesi';
    case 'cevap_dilekcesi':
      return 'Cevap Dilekçesi';
    case 'istinaf_dilekcesi':
      return 'İstinaf Dilekçesi';
    case 'temyiz_dilekcesi':
      return 'Temyiz Dilekçesi';
    case 'bilir_kisi_raporu':
      return 'Bilirkişi Raporu';
    case 'hukuki_mutalaa':
      return 'Hukuki Mütalaa';
    case 'delil_listesi':
      return 'Delil Listesi';
    case 'durusma_tutanagi':
      return 'Duruşma Tutanağı';
    case 'ihtarname':
      return 'İhtarname';
    case 'genel_dilekce':
      return 'Genel Dilekçe';
    case 'aciklama_metni':
      return 'Açıklama Metni';
    case 'kapanis_aciklamasi':
      return 'Kapanış Açıklaması';
    default:
      return type;
  }
}

String paragraphTypeLabel(String type) {
  switch (type) {
    case 'giris':
      return 'Giriş';
    case 'aciklama':
      return 'Açıklama';
    case 'hukuki_dayanak':
      return 'Hukuki Dayanak';
    case 'delil_sunumu':
      return 'Delil Sunumu';
    case 'talep_sonuc':
      return 'Talep Sonuç';
    case 'sonuc':
      return 'Sonuç';
    case 'ara_baslik':
      return 'Ara Başlık';
    case 'alinti':
      return 'Alıntı';
    case 'kapanis':
      return 'Kapanış';
    default:
      return type;
  }
}

String statusLabel(String status) {
  switch (status) {
    case 'draft':
      return 'Taslak';
    case 'reviewing':
      return 'İnceleniyor';
    case 'finalized':
      return 'Sonuçlandı';
    case 'generating':
      return 'Oluşturuluyor';
    case 'failed':
      return 'Başarısız';
    default:
      return status;
  }
}

String changeTypeLabel(String changeType) {
  switch (changeType) {
    case 'created':
      return 'Oluşturuldu';
    case 'edited':
      return 'Düzenlendi';
    case 'ai_generated':
      return 'Yapay Zeka';
    case 'restored':
      return 'Geri yüklendi';
    default:
      return changeType;
  }
}

String decisionLabelText(String decision) {
  switch (decision) {
    case 'accepted':
      return 'Kabul edildi';
    case 'changes_requested':
      return 'Değişiklik istendi';
    case 'rejected':
      return 'Reddedildi';
    default:
      return decision;
  }
}

String reasonCodeLabelText(String reasonCode) {
  switch (reasonCode) {
    case 'legal_error':
      return 'Hukuki hata';
    case 'factual_error':
      return 'Maddi hata';
    case 'formatting':
      return 'Biçimlendirme';
    case 'missing_reference':
      return 'Eksik atıf';
    case 'tone_language':
      return 'Üslup / Dil';
    case 'other':
      return 'Diğer';
    default:
      return reasonCode;
  }
}

String stageLabelText(String stage) {
  switch (stage) {
    case 'queued':
      return 'Sırada';
    case 'planning':
      return 'Planlanıyor';
    case 'generating':
      return 'Oluşturuluyor';
    case 'assembling':
      return 'Birleştiriliyor';
    case 'formatting':
      return 'Biçimlendiriliyor';
    default:
      return stage;
  }
}

class DraftItem {
  const DraftItem({
    required this.id,
    required this.caseId,
    required this.title,
    required this.draftType,
    required this.status,
    required this.paragraphCount,
    required this.version,
    required this.createdAt,
    required this.updatedAt,
    this.finalizedAt,
    this.supersedesDraftId,
  });

  final String id;
  final String caseId;
  final String title;
  final String draftType;
  final String status;
  final int paragraphCount;
  final int version;
  final String createdAt;
  final String updatedAt;
  final String? finalizedAt;
  final String? supersedesDraftId;

  String get label => draftTypeLabel(draftType);

  bool get isEditable => status == 'draft' || status == 'reviewing';

  factory DraftItem.fromDto(DraftDto dto) => DraftItem(
    id: dto.id,
    caseId: dto.caseId,
    title: dto.title,
    draftType: dto.draftType,
    status: dto.status,
    paragraphCount: dto.paragraphCount,
    version: dto.version,
    createdAt: dto.createdAt,
    updatedAt: dto.updatedAt,
    finalizedAt: dto.finalizedAt,
    supersedesDraftId: dto.supersedesDraftId,
  );
}

class DraftDetailItem {
  const DraftDetailItem({
    required this.id,
    required this.caseId,
    required this.title,
    required this.draftType,
    required this.status,
    required this.paragraphCount,
    required this.version,
    required this.createdAt,
    required this.updatedAt,
    this.finalizedAt,
    this.supersedesDraftId,
    this.paragraphs = const <DraftParagraphItem>[],
    this.issueLinks = const <DraftIssueLinkItem>[],
    this.sourceLinks = const <DraftSourceLinkItem>[],
  });

  final String id;
  final String caseId;
  final String title;
  final String draftType;
  final String status;
  final int paragraphCount;
  final int version;
  final String createdAt;
  final String updatedAt;
  final String? finalizedAt;
  final String? supersedesDraftId;
  final List<DraftParagraphItem> paragraphs;
  final List<DraftIssueLinkItem> issueLinks;
  final List<DraftSourceLinkItem> sourceLinks;

  String get label => draftTypeLabel(draftType);

  bool get isEditable => status == 'draft' || status == 'reviewing';

  factory DraftDetailItem.fromDto(DraftDetailDto dto) => DraftDetailItem(
    id: dto.id,
    caseId: dto.caseId,
    title: dto.title,
    draftType: dto.draftType,
    status: dto.status,
    paragraphCount: dto.paragraphCount,
    version: dto.version,
    createdAt: dto.createdAt,
    updatedAt: dto.updatedAt,
    finalizedAt: dto.finalizedAt,
    supersedesDraftId: dto.supersedesDraftId,
    paragraphs: dto.paragraphs.map(DraftParagraphItem.fromDto).toList(),
    issueLinks: dto.issueLinks.map(DraftIssueLinkItem.fromDto).toList(),
    sourceLinks: dto.sourceLinks.map(DraftSourceLinkItem.fromDto).toList(),
  );
}

class DraftParagraphItem {
  const DraftParagraphItem({
    required this.id,
    required this.draftId,
    required this.order,
    required this.paragraphType,
    required this.text,
    required this.version,
    required this.createdAt,
    required this.updatedAt,
    required this.verificationStatus,
    this.effectiveTrust,
    this.currentRevisionId,
    this.currentReviewId,
  });

  final String id;
  final String draftId;
  final int order;
  final String paragraphType;
  final String text;
  final int version;
  final String createdAt;
  final String updatedAt;
  final String verificationStatus;
  final double? effectiveTrust;
  final String? currentRevisionId;
  final String? currentReviewId;

  String get label => paragraphTypeLabel(paragraphType);

  factory DraftParagraphItem.fromDto(DraftParagraphDto dto) =>
      DraftParagraphItem(
        id: dto.id,
        draftId: dto.draftId,
        order: dto.order,
        paragraphType: dto.paragraphType,
        text: dto.text,
        version: dto.version,
        createdAt: dto.createdAt,
        updatedAt: dto.updatedAt,
        verificationStatus: dto.verificationStatus,
        effectiveTrust: dto.effectiveTrust,
        currentRevisionId: dto.currentRevisionId,
        currentReviewId: dto.currentReviewId,
      );
}

class DraftIssueLinkItem {
  const DraftIssueLinkItem({
    required this.id,
    required this.draftParagraphId,
    required this.legalIssueId,
    required this.relationType,
    required this.createdAt,
    required this.version,
  });

  final String id;
  final String draftParagraphId;
  final String legalIssueId;
  final String relationType;
  final String createdAt;
  final int version;

  factory DraftIssueLinkItem.fromDto(DraftIssueLinkDto dto) =>
      DraftIssueLinkItem(
        id: dto.id,
        draftParagraphId: dto.draftParagraphId,
        legalIssueId: dto.legalIssueId,
        relationType: dto.relationType,
        createdAt: dto.createdAt,
        version: dto.version,
      );
}

class DraftSourceLinkItem {
  const DraftSourceLinkItem({
    required this.id,
    required this.draftParagraphId,
    required this.sourceRecordId,
    required this.sourceVersionId,
    this.sourceParagraphId,
    required this.usageType,
    required this.quoteHash,
    required this.verificationStatus,
    this.effectiveTrust,
    required this.createdAt,
    required this.version,
  });

  final String id;
  final String draftParagraphId;
  final String sourceRecordId;
  final String sourceVersionId;
  final String? sourceParagraphId;
  final String usageType;
  final String quoteHash;
  final String verificationStatus;
  final double? effectiveTrust;
  final String createdAt;
  final int version;

  bool get isVerified =>
      verificationStatus == 'verified_official' ||
      verificationStatus == 'verified_secondary';

  factory DraftSourceLinkItem.fromDto(DraftSourceLinkDto dto) =>
      DraftSourceLinkItem(
        id: dto.id,
        draftParagraphId: dto.draftParagraphId,
        sourceRecordId: dto.sourceRecordId,
        sourceVersionId: dto.sourceVersionId,
        sourceParagraphId: dto.sourceParagraphId,
        usageType: dto.usageType,
        quoteHash: dto.quoteHash,
        verificationStatus: dto.verificationStatus,
        effectiveTrust: dto.effectiveTrust,
        createdAt: dto.createdAt,
        version: dto.version,
      );
}

class DraftRevisionItem {
  const DraftRevisionItem({
    required this.id,
    required this.draftParagraphId,
    required this.revisionNumber,
    required this.changeType,
    required this.createdBy,
    required this.createdAt,
    required this.textHash,
    required this.currentRevision,
    required this.text,
  });

  final String id;
  final String draftParagraphId;
  final int revisionNumber;
  final String changeType;
  final String createdBy;
  final String createdAt;
  final String textHash;
  final bool currentRevision;
  final String text;

  String get label => changeTypeLabel(changeType);

  factory DraftRevisionItem.fromDto(DraftRevisionDto dto) => DraftRevisionItem(
    id: dto.id,
    draftParagraphId: dto.draftParagraphId,
    revisionNumber: dto.revisionNumber,
    changeType: dto.changeType,
    createdBy: dto.createdBy,
    createdAt: dto.createdAt,
    textHash: dto.textHash,
    currentRevision: dto.currentRevision,
    text: dto.text,
  );
}

class DraftReviewEventItem {
  const DraftReviewEventItem({
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
  final String draftParagraphId;
  final String paragraphRevisionId;
  final String decision;
  final String reasonCode;
  final String reviewerUserId;
  final int paragraphVersion;
  final String createdAt;

  String get decisionLabel => decisionLabelText(decision);

  String get reasonCodeLabel => reasonCodeLabelText(reasonCode);

  factory DraftReviewEventItem.fromDto(DraftReviewEventDto dto) =>
      DraftReviewEventItem(
        id: dto.id,
        draftParagraphId: dto.draftParagraphId,
        paragraphRevisionId: dto.paragraphRevisionId,
        decision: dto.decision,
        reasonCode: dto.reasonCode,
        reviewerUserId: dto.reviewerUserId,
        paragraphVersion: dto.paragraphVersion,
        createdAt: dto.createdAt,
      );
}

class DraftReadinessItem {
  const DraftReadinessItem({
    required this.status,
    required this.blockedReasons,
    required this.warnings,
    required this.metrics,
  });

  final String status;
  final List<String> blockedReasons;
  final List<String> warnings;
  final Map<String, dynamic> metrics;

  bool get isBlocked => blockedReasons.isNotEmpty;

  bool get isReady => status == 'ready';

  factory DraftReadinessItem.fromDto(DraftReadinessDto dto) =>
      DraftReadinessItem(
        status: dto.status,
        blockedReasons: dto.blockedReasons,
        warnings: dto.warnings,
        metrics: dto.metrics,
      );
}

class DraftGenerationJobItem {
  const DraftGenerationJobItem({
    required this.jobId,
    required this.draftId,
    required this.status,
    required this.stage,
    required this.progressPercent,
    required this.requestedDraftVersion,
    this.resultDraftVersion,
    required this.providerName,
    required this.modelName,
    required this.safeErrorCode,
    required this.safeMetrics,
    required this.queuedAt,
    this.startedAt,
    this.completedAt,
  });

  final String jobId;
  final String draftId;
  final String status;
  final String stage;
  final int progressPercent;
  final int requestedDraftVersion;
  final int? resultDraftVersion;
  final String providerName;
  final String modelName;
  final String safeErrorCode;
  final Map<String, dynamic> safeMetrics;
  final String queuedAt;
  final String? startedAt;
  final String? completedAt;

  bool get isTerminal => status == 'succeeded' || status == 'failed';

  String get stageLabel => stageLabelText(stage);

  factory DraftGenerationJobItem.fromDto(DraftGenerationJobDto dto) =>
      DraftGenerationJobItem(
        jobId: dto.jobId,
        draftId: dto.draftId,
        status: dto.status,
        stage: dto.stage,
        progressPercent: dto.progressPercent,
        requestedDraftVersion: dto.requestedDraftVersion,
        resultDraftVersion: dto.resultDraftVersion,
        providerName: dto.providerName,
        modelName: dto.modelName,
        safeErrorCode: dto.safeErrorCode,
        safeMetrics: dto.safeMetrics,
        queuedAt: dto.queuedAt,
        startedAt: dto.startedAt,
        completedAt: dto.completedAt,
      );
}

class DraftValidationItem {
  const DraftValidationItem({
    required this.valid,
    required this.blockingErrors,
    required this.warnings,
    required this.metrics,
  });

  final bool valid;
  final List<String> blockingErrors;
  final List<String> warnings;
  final Map<String, dynamic> metrics;

  factory DraftValidationItem.fromDto(DraftValidationDto dto) =>
      DraftValidationItem(
        valid: dto.valid,
        blockingErrors: dto.blockingErrors,
        warnings: dto.warnings,
        metrics: dto.metrics,
      );
}

class DraftFinalizeItem {
  const DraftFinalizeItem({
    required this.id,
    required this.caseId,
    required this.status,
    required this.finalizedAt,
    required this.version,
    required this.paragraphCount,
    required this.issueLinkCount,
    required this.sourceLinkCount,
    required this.markedSourceUsageCount,
  });

  final String id;
  final String caseId;
  final String status;
  final String finalizedAt;
  final int version;
  final int paragraphCount;
  final int issueLinkCount;
  final int sourceLinkCount;
  final int markedSourceUsageCount;

  factory DraftFinalizeItem.fromDto(DraftFinalizeDto dto) => DraftFinalizeItem(
    id: dto.id,
    caseId: dto.caseId,
    status: dto.status,
    finalizedAt: dto.finalizedAt,
    version: dto.version,
    paragraphCount: dto.paragraphCount,
    issueLinkCount: dto.issueLinkCount,
    sourceLinkCount: dto.sourceLinkCount,
    markedSourceUsageCount: dto.markedSourceUsageCount,
  );
}

class DraftCreateResultItem {
  const DraftCreateResultItem({
    required this.id,
    required this.caseId,
    required this.title,
    required this.draftType,
    required this.status,
    required this.version,
  });

  final String id;
  final String caseId;
  final String title;
  final String draftType;
  final String status;
  final int version;

  String get label => draftTypeLabel(draftType);

  factory DraftCreateResultItem.fromDto(DraftDto dto) => DraftCreateResultItem(
    id: dto.id,
    caseId: dto.caseId,
    title: dto.title,
    draftType: dto.draftType,
    status: dto.status,
    version: dto.version,
  );
}

class DraftPlanItem {
  const DraftPlanItem({
    required this.draftId,
    required this.draftType,
    required this.sections,
  });

  final String draftId;
  final String draftType;
  final List<SectionPlanEntryItem> sections;

  factory DraftPlanItem.fromDto(DraftPlanDto dto) => DraftPlanItem(
    draftId: dto.draftId,
    draftType: dto.draftType,
    sections: dto.sections.map(SectionPlanEntryItem.fromDto).toList(),
  );
}

class SectionPlanEntryItem {
  const SectionPlanEntryItem({
    required this.sectionTitle,
    required this.sectionType,
    required this.recommendedParagraphs,
    required this.instructions,
  });

  final String sectionTitle;
  final String sectionType;
  final int recommendedParagraphs;
  final String instructions;

  factory SectionPlanEntryItem.fromDto(SectionPlanEntryDto dto) =>
      SectionPlanEntryItem(
        sectionTitle: dto.sectionTitle,
        sectionType: dto.sectionType,
        recommendedParagraphs: dto.recommendedParagraphs,
        instructions: dto.instructions,
      );
}

class DraftGenerateItem {
  const DraftGenerateItem({
    required this.draftId,
    required this.paragraphId,
    required this.text,
    required this.metadata,
  });

  final String draftId;
  final String paragraphId;
  final String text;
  final Map<String, dynamic> metadata;

  factory DraftGenerateItem.fromDto(DraftGenerateDto dto) => DraftGenerateItem(
    draftId: dto.draftId,
    paragraphId: dto.paragraphId,
    text: dto.text,
    metadata: dto.metadata,
  );
}
