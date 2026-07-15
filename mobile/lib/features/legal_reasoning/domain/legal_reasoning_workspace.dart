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

  bool get isEmpty => issues.isEmpty;

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
