class LegalIssueSummary {
  const LegalIssueSummary({
    required this.id,
    required this.title,
    required this.status,
    required this.supportState,
    required this.version,
    this.parentIssueId,
    this.description = '',
    this.stale = false,
  });

  final String id;
  final String? parentIssueId;
  final String title;
  final String description;
  final String status;
  final String supportState;
  final bool stale;
  final int version;

  factory LegalIssueSummary.fromJson(Map<String, dynamic> json) =>
      LegalIssueSummary(
        id: json['id'] as String,
        parentIssueId: json['parent_issue_id'] as String?,
        title: json['title'] as String? ?? '',
        description: json['description'] as String? ?? '',
        status: json['status'] as String? ?? 'identified',
        supportState: json['support_state'] as String? ?? 'uncertain',
        stale: json['stale'] as bool? ?? false,
        version: json['version'] as int? ?? 1,
      );
}

class LegalReasoningWorkspace {
  const LegalReasoningWorkspace({
    required this.caseId,
    required this.issues,
    required this.burdens,
    required this.counterarguments,
    required this.sourceLinks,
    required this.evidenceLinks,
    required this.factLinks,
    required this.missingInformation,
    required this.unsupportedClaims,
    required this.stale,
    this.precedentPool,
  });

  final String caseId;
  final List<LegalIssueSummary> issues;
  final List<Map<String, dynamic>> burdens;
  final List<Map<String, dynamic>> counterarguments;
  final List<Map<String, dynamic>> sourceLinks;
  final List<Map<String, dynamic>> evidenceLinks;
  final List<Map<String, dynamic>> factLinks;
  final List<Map<String, dynamic>> missingInformation;
  final List<Map<String, dynamic>> unsupportedClaims;
  final bool stale;
  final PrecedentPoolWorkspace? precedentPool;

  bool get isEmpty => issues.isEmpty;

  LegalReasoningWorkspace withPrecedentPool(PrecedentPoolWorkspace? pool) =>
      LegalReasoningWorkspace(
        caseId: caseId,
        issues: issues,
        burdens: burdens,
        counterarguments: counterarguments,
        sourceLinks: sourceLinks,
        evidenceLinks: evidenceLinks,
        factLinks: factLinks,
        missingInformation: missingInformation,
        unsupportedClaims: unsupportedClaims,
        stale: stale,
        precedentPool: pool,
      );

  factory LegalReasoningWorkspace.fromJson(
    Map<String, dynamic> json, {
    List<LegalIssueSummary>? issueSummaries,
  }) {
    List<Map<String, dynamic>> maps(String key) =>
        (json[key] as List<dynamic>? ?? const <dynamic>[])
            .map((dynamic value) => Map<String, dynamic>.from(value as Map))
            .toList(growable: false);
    return LegalReasoningWorkspace(
      caseId: json['case_id'] as String? ?? '',
      stale: json['stale'] as bool? ?? false,
      issues:
          issueSummaries ??
          maps('issues').map(LegalIssueSummary.fromJson).toList(),
      burdens: maps('burdens'),
      counterarguments: maps('counterarguments'),
      sourceLinks: maps('source_links'),
      evidenceLinks: maps('evidence_links'),
      factLinks: maps('fact_links'),
      missingInformation: maps('missing_information'),
      unsupportedClaims: maps('unsupported_claims'),
    );
  }
}

class PrecedentPoolWorkspace {
  const PrecedentPoolWorkspace({
    required this.pool,
    required this.decisions,
    required this.analyses,
  });

  final PrecedentPoolSummary pool;
  final List<PrecedentDecision> decisions;
  final List<PrecedentAnalysis> analyses;

  bool get isEmpty => decisions.isEmpty;
}

class PrecedentPoolSummary {
  const PrecedentPoolSummary({
    required this.id,
    required this.providerStatus,
    required this.status,
    required this.candidateCap,
    required this.totalDiscovered,
    required this.totalIngested,
    required this.totalDuplicate,
    required this.totalFailed,
    required this.profileSummary,
    this.safeErrorCode = '',
  });

  final String id;
  final String providerStatus;
  final String status;
  final int candidateCap;
  final int totalDiscovered;
  final int totalIngested;
  final int totalDuplicate;
  final int totalFailed;
  final String safeErrorCode;
  final Map<String, dynamic> profileSummary;

  bool get degraded => providerStatus == 'degraded_existing_corpus';
  bool get partial => providerStatus == 'completed_with_errors';

  factory PrecedentPoolSummary.fromJson(Map<String, dynamic> json) =>
      PrecedentPoolSummary(
        id: json['id'] as String? ?? json['pool_id'] as String? ?? '',
        providerStatus: json['provider_status'] as String? ?? '',
        status: json['status'] as String? ?? '',
        candidateCap: json['candidate_cap'] as int? ?? 0,
        totalDiscovered: json['total_discovered'] as int? ?? 0,
        totalIngested: json['total_ingested'] as int? ?? 0,
        totalDuplicate: json['total_duplicate'] as int? ?? 0,
        totalFailed: json['total_failed'] as int? ?? 0,
        safeErrorCode: json['safe_error_code'] as String? ?? '',
        profileSummary: Map<String, dynamic>.from(
          json['profile_summary'] as Map? ?? const <String, dynamic>{},
        ),
      );
}

class PrecedentDecision {
  const PrecedentDecision({
    required this.id,
    required this.sourceRecordId,
    required this.sourceVersionId,
    required this.retrievalRank,
    required this.scores,
    required this.title,
    required this.court,
    required this.chamber,
    required this.caseNumber,
    required this.decisionNumber,
    required this.decisionDate,
    required this.officialUrl,
    required this.relevantParagraph,
    required this.matchReasons,
  });

  final String id;
  final String sourceRecordId;
  final String sourceVersionId;
  final int retrievalRank;
  final Map<String, dynamic> scores;
  final String title;
  final String court;
  final String chamber;
  final String caseNumber;
  final String decisionNumber;
  final String decisionDate;
  final String officialUrl;
  final String relevantParagraph;
  final List<String> matchReasons;

  double get relevanceScore =>
      (scores['final_score'] as num?)?.toDouble() ?? 0.0;

  factory PrecedentDecision.fromJson(Map<String, dynamic> json) =>
      PrecedentDecision(
        id: json['id'] as String? ?? '',
        sourceRecordId: json['source_record_id'] as String? ?? '',
        sourceVersionId: json['source_version_id'] as String? ?? '',
        retrievalRank: json['retrieval_rank'] as int? ?? 0,
        scores: Map<String, dynamic>.from(
          json['scores'] as Map? ?? const <String, dynamic>{},
        ),
        title: json['title'] as String? ?? '',
        court: json['court'] as String? ?? '',
        chamber: json['chamber'] as String? ?? '',
        caseNumber: json['case_number'] as String? ?? '',
        decisionNumber: json['decision_number'] as String? ?? '',
        decisionDate: json['decision_date'] as String? ?? '',
        officialUrl: json['official_url'] as String? ?? '',
        relevantParagraph: json['relevant_paragraph'] as String? ?? '',
        matchReasons: (json['match_reasons'] as List<dynamic>? ?? const [])
            .map((dynamic value) => value.toString())
            .toList(growable: false),
      );
}

class PrecedentAnalysis {
  const PrecedentAnalysis({
    required this.poolDecisionId,
    required this.analysis,
  });

  final String poolDecisionId;
  final Map<String, dynamic> analysis;

  factory PrecedentAnalysis.fromJson(Map<String, dynamic> json) =>
      PrecedentAnalysis(
        poolDecisionId: json['pool_decision_id'] as String? ?? '',
        analysis: Map<String, dynamic>.from(
          json['analysis'] as Map? ?? const <String, dynamic>{},
        ),
      );
}
