import '../../../core/network/api_client.dart';
import '../domain/legal_reasoning_workspace.dart';

class LegalReasoningRepository {
  const LegalReasoningRepository(this._client);

  final ApiClient _client;

  Future<LegalReasoningWorkspace> load(String caseId) async {
    final List<dynamic> issueJson = await _client.getJson<List<dynamic>>(
      '/api/v1/cases/$caseId/legal-issues',
    );
    final List<LegalIssueSummary> issues = issueJson
        .map(
          (dynamic value) => LegalIssueSummary.fromJson(
            Map<String, dynamic>.from(value as Map),
          ),
        )
        .toList(growable: false);
    if (issues.isEmpty) {
      return LegalReasoningWorkspace(
        caseId: caseId,
        issues: const <LegalIssueSummary>[],
        burdens: const <Map<String, dynamic>>[],
        counterarguments: const <Map<String, dynamic>>[],
        sourceLinks: const <Map<String, dynamic>>[],
        evidenceLinks: const <Map<String, dynamic>>[],
        factLinks: const <Map<String, dynamic>>[],
        missingInformation: const <Map<String, dynamic>>[],
        unsupportedClaims: const <Map<String, dynamic>>[],
        stale: false,
      ).withPrecedentPool(await _loadPrecedentPool(caseId));
    }
    final Map<String, dynamic> graph = await _client
        .getJson<Map<String, dynamic>>(
          '/api/v1/legal-issues/${issues.first.id}/graph',
        );
    return LegalReasoningWorkspace.fromJson(
      graph,
      issueSummaries: issues,
    ).withPrecedentPool(await _loadPrecedentPool(caseId));
  }

  Future<PrecedentPoolWorkspace?> _loadPrecedentPool(String caseId) async {
    try {
      final List<dynamic> poolsJson = await _client.getJson<List<dynamic>>(
        '/api/v1/cases/$caseId/precedent-pools',
      );
      if (poolsJson.isEmpty) return null;
      final PrecedentPoolSummary pool = PrecedentPoolSummary.fromJson(
        Map<String, dynamic>.from(poolsJson.first as Map),
      );
      final List<dynamic> decisionsJson = await _client.getJson<List<dynamic>>(
        '/api/v1/precedent-pools/${pool.id}/decisions',
      );
      final Map<String, dynamic> analysesJson = await _client
          .getJson<Map<String, dynamic>>(
            '/api/v1/precedent-pools/${pool.id}/analyses',
          );
      return PrecedentPoolWorkspace(
        pool: pool,
        decisions: decisionsJson
            .map(
              (dynamic value) => PrecedentDecision.fromJson(
                Map<String, dynamic>.from(value as Map),
              ),
            )
            .toList(growable: false),
        analyses: (analysesJson['items'] as List<dynamic>? ?? const [])
            .map(
              (dynamic value) => PrecedentAnalysis.fromJson(
                Map<String, dynamic>.from(value as Map),
              ),
            )
            .toList(growable: false),
      );
    } catch (_) {
      return null;
    }
  }

  Future<void> findPrecedents(LegalReasoningWorkspace workspace) async {
    final String caseText = _caseText(workspace);
    final Map<String, dynamic> response = await _client
        .postJson<Map<String, dynamic>>(
          '/api/v1/search/dynamic-pool',
          body: <String, dynamic>{
            'case_id': workspace.caseId,
            'case_text': caseText,
            'preferred_relief': workspace.unsupportedClaims
                .map((Map<String, dynamic> item) => item['title']?.toString())
                .whereType<String>()
                .take(3)
                .toList(growable: false),
            'max_queries': 3,
            'max_candidates': 30,
            'shortlist_size': 8,
          },
        );
    final String? poolId =
        response['pool_id'] as String? ?? (response['id'] as String?);
    if (poolId != null && poolId.isNotEmpty) {
      await _client.postJson<Map<String, dynamic>>(
        '/api/v1/precedent-pools/$poolId/analyze',
        body: const <String, dynamic>{'force': false},
      );
    }
  }

  String _caseText(LegalReasoningWorkspace workspace) {
    final List<String> lines =
        <String>[
              for (final LegalIssueSummary issue in workspace.issues)
                '${issue.title}. ${issue.description}',
              for (final Map<String, dynamic> item
                  in workspace.missingInformation)
                'Eksik bilgi: ${item['label'] ?? ''}',
              for (final Map<String, dynamic> item
                  in workspace.unsupportedClaims)
                'Desteksiz iddia: ${item['title'] ?? ''}',
            ]
            .map((String value) => value.trim())
            .where((String value) => value.isNotEmpty)
            .toList(growable: false);
    final String text = lines.join('\n');
    if (text.length >= 20) return text;
    return 'Dosya hukuki uyuşmazlığı için emsal Yargıtay kararları aranacak.';
  }

  Future<void> rebuild(String caseId) => _client.postJson<Map<String, dynamic>>(
    '/api/v1/cases/$caseId/legal-issues/rebuild',
    body: const <String, dynamic>{'prompt_version': 'p2.8b-legal-reasoning-1'},
  );

  Future<void> updateIssue(LegalIssueSummary issue, String status) async {
    await _client.patchJson<Map<String, dynamic>>(
      '/api/v1/legal-issues/${issue.id}',
      body: <String, dynamic>{'version': issue.version, 'status': status},
    );
  }
}
