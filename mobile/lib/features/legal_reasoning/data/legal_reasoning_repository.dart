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
      );
    }
    final Map<String, dynamic> graph = await _client
        .getJson<Map<String, dynamic>>(
          '/api/v1/legal-issues/${issues.first.id}/graph',
        );
    return LegalReasoningWorkspace.fromJson(graph, issueSummaries: issues);
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
