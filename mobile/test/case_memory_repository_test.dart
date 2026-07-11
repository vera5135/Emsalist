import 'package:emsalist_mobile/features/case_memory/data/case_memory_api.dart';
import 'package:emsalist_mobile/features/case_memory/data/case_memory_repository.dart';
import 'package:emsalist_mobile/features/case_memory/domain/case_memory.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_api_client.dart';

const String _caseId = 'c1';
const String _base = '/api/v1/cases/$_caseId/memory';

Map<String, dynamic> _memoryJson({
  String overall = 'low',
  List<Map<String, dynamic>> facts = const <Map<String, dynamic>>[],
  List<Map<String, dynamic>> contradictions = const <Map<String, dynamic>>[],
  List<Map<String, dynamic>> missing = const <Map<String, dynamic>>[],
  List<Map<String, dynamic>> risks = const <Map<String, dynamic>>[],
}) {
  return <String, dynamic>{
    'case_id': _caseId,
    'overall_risk_level': overall,
    'facts': facts,
    'timeline': <dynamic>[],
    'missing_information': missing,
    'contradictions': contradictions,
    'risks': risks,
  };
}

CaseMemoryRepository _repo(FakeApiClient client) =>
    CaseMemoryRepository(CaseMemoryApi(client));

void main() {
  test('loadMemory maps aggregate and overall risk', () async {
    final FakeApiClient client = FakeApiClient()
      ..whenGet(
        _base,
        _memoryJson(
          overall: 'high',
          facts: <Map<String, dynamic>>[
            <String, dynamic>{
              'id': 'f1',
              'case_id': _caseId,
              'fact_type': 'sale_amount',
              'value': '150000',
              'verification_status': 'suggested',
              'version': 1,
            },
          ],
        ),
      );

    final CaseMemory memory = await _repo(client).loadMemory(_caseId);

    expect(memory.overallRiskLevel, 'high');
    expect(memory.facts, hasLength(1));
    expect(memory.facts.first.isConfirmed, isFalse);
  });

  test('confirmed status maps to isConfirmed', () async {
    final FakeApiClient client = FakeApiClient()
      ..whenGet(
        _base,
        _memoryJson(
          facts: <Map<String, dynamic>>[
            <String, dynamic>{
              'id': 'f1',
              'case_id': _caseId,
              'fact_type': 'x',
              'value': 'v',
              'verification_status': 'user_confirmed',
              'version': 2,
            },
          ],
        ),
      );
    final CaseMemory memory = await _repo(client).loadMemory(_caseId);
    expect(memory.facts.first.isConfirmed, isTrue);
  });

  test('confirmFact posts to confirm endpoint', () async {
    final FakeApiClient client = FakeApiClient()
      ..whenPost('$_base/facts/f1/confirm', <String, dynamic>{
        'id': 'f1',
        'case_id': _caseId,
        'fact_type': 'x',
        'value': 'v',
        'verification_status': 'user_confirmed',
        'version': 2,
      });
    await _repo(client).confirmFact(_caseId, 'f1');
    expect(client.postPaths, contains('$_base/facts/f1/confirm'));
  });

  test('rejectFact posts to reject endpoint', () async {
    final FakeApiClient client = FakeApiClient()
      ..whenPost('$_base/facts/f1/reject', <String, dynamic>{
        'id': 'f1',
        'case_id': _caseId,
        'fact_type': 'x',
        'value': 'v',
        'verification_status': 'rejected',
        'version': 2,
      });
    await _repo(client).rejectFact(_caseId, 'f1');
    expect(client.postPaths, contains('$_base/facts/f1/reject'));
  });

  test('resolveContradiction forwards resolution_fact_id', () async {
    final FakeApiClient client = FakeApiClient()
      ..whenPost('$_base/contradictions/x1/resolve', <String, dynamic>{
        'id': 'x1',
        'case_id': _caseId,
        'contradiction_type': 'value_mismatch',
        'description': 'd',
        'fact_ids': <String>['f1', 'f2'],
        'severity': 'high',
        'status': 'resolved',
      });

    await _repo(
      client,
    ).resolveContradiction(_caseId, 'x1', resolutionFactId: 'f1');

    final Object? body = client.postBodies.first;
    expect((body! as Map<String, dynamic>)['resolution_fact_id'], 'f1');
  });

  test('updateFactValue forwards version + value', () async {
    final FakeApiClient client = FakeApiClient()
      ..whenPost('$_base/facts/f1', <String, dynamic>{
        'id': 'f1',
        'case_id': _caseId,
        'fact_type': 'x',
        'value': 'new',
        'verification_status': 'suggested',
        'version': 3,
      });
    await _repo(
      client,
    ).updateFactValue(_caseId, 'f1', version: 2, value: 'new');
    final Object? body = client.postBodies.first;
    expect((body! as Map<String, dynamic>)['version'], 2);
    expect((body as Map<String, dynamic>)['value'], 'new');
  });
}
