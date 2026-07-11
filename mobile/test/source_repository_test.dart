import 'package:emsalist_mobile/features/sources/data/source_api.dart';
import 'package:emsalist_mobile/features/sources/data/source_repository.dart';
import 'package:emsalist_mobile/features/sources/domain/source_item.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_api_client.dart';

const String _caseId = 'c1';

SourceRepository _repo(FakeApiClient client) =>
    SourceRepository(SourceApi(client));

Map<String, dynamic> _record({
  String id = 's1',
  String status = 'verified_official',
  String temporal = 'valid',
}) {
  return <String, dynamic>{
    'id': id,
    'source_type': 'supreme_court_decision',
    'title': 'Yargıtay 13. HD',
    'court': 'Yargıtay',
    'chamber': '13. HD',
    'case_number': '2020/123',
    'decision_number': '2021/456',
    'decision_date': '2021-06-12',
    'official_url': 'https://karararama.yargitay.gov.tr/x',
    'verification_status': status,
    'temporal_status': temporal,
    'current_version_id': 'v1',
    'version': 1,
  };
}

void main() {
  test('listSources maps records + badge', () async {
    final FakeApiClient client = FakeApiClient()
      ..whenGet(SourceApi.sourcesPath, <String, dynamic>{
        'items': <dynamic>[_record()],
        'total': 1,
        'has_more': false,
      });
    final list = await _repo(client).listSources();
    expect(list, hasLength(1));
    expect(list.first.isOfficial, isTrue);
    expect(list.first.badge, 'Resmî kaynaktan doğrulandı');
  });

  test('verification badge labels are user-facing (no snake_case)', () {
    expect(
      verificationBadgeLabel('verified_official'),
      'Resmî kaynaktan doğrulandı',
    );
    expect(verificationBadgeLabel('needs_review'), 'İnceleme gerekli');
    expect(verificationBadgeLabel('conflicting'), 'Çelişkili kaynak');
    expect(verificationBadgeLabel('quarantined'), 'Kullanıma kapalı');
    expect(verificationBadgeLabel('repealed'), 'Yürürlükten kaldırıldı');
    // Never leak the raw internal token.
    expect(verificationBadgeLabel('verified_official').contains('_'), isFalse);
  });

  test('paragraphs map article number and page', () async {
    final FakeApiClient client = FakeApiClient()
      ..whenGetRaw('${SourceApi.sourcesPath}/s1/paragraphs', <dynamic>[
        <String, dynamic>{
          'id': 'p1',
          'paragraph_index': 1,
          'text': 'Madde metni',
          'article_number': '219',
          'page': null,
        },
      ]);
    final list = await _repo(client).paragraphs('s1');
    expect(list.first.articleNumber, '219');
    expect(list.first.page, isNull);
  });

  test('addCaseSource forwards ids + reason', () async {
    final FakeApiClient client = FakeApiClient()
      ..whenPost('/api/v1/cases/$_caseId/sources', <String, dynamic>{
        'id': 'u1',
        'case_id': _caseId,
        'source_record_id': 's1',
        'source_version_id': 'v1',
        'used_in_final_draft': false,
        'verification_status': 'verified_official',
      });
    await _repo(client).addCaseSource(
      _caseId,
      sourceRecordId: 's1',
      sourceVersionId: 'v1',
      reason: 'dayanak',
    );
    final Object? body = client.postBodies.first;
    expect((body! as Map<String, dynamic>)['source_record_id'], 's1');
    expect((body as Map<String, dynamic>)['reason'], 'dayanak');
  });

  test('caseSources maps usage with used_in_final_draft false', () async {
    final FakeApiClient client = FakeApiClient()
      ..whenGet('/api/v1/cases/$_caseId/sources', <String, dynamic>{
        'items': <dynamic>[
          <String, dynamic>{
            'id': 'u1',
            'case_id': _caseId,
            'source_title': 'Yargıtay 13. HD',
            'source_type': 'supreme_court_decision',
            'verification_status': 'verified_official',
            'used_in_final_draft': false,
            'reason': 'dayanak',
          },
        ],
      });
    final list = await _repo(client).caseSources(_caseId);
    expect(list, hasLength(1));
    expect(list.first.usedInFinalDraft, isFalse);
    expect(list.first.badge, 'Resmî kaynaktan doğrulandı');
  });

  test('removeCaseSource hits delete endpoint', () async {
    final FakeApiClient client = FakeApiClient();
    await _repo(client).removeCaseSource(_caseId, 'u1');
    expect(client.deletePaths, contains('/api/v1/cases/$_caseId/sources/u1'));
  });

  test('officialTracking maps affected case count', () async {
    final FakeApiClient client = FakeApiClient()
      ..whenGet(SourceApi.trackingPath, <String, dynamic>{
        'items': <dynamic>[
          <String, dynamic>{
            'source_id': 's1',
            'title': 'Türk Borçlar Kanunu',
            'source_type': 'legislation',
            'affected_case_count': 3,
            'new_version_detected': true,
            'requires_review': false,
          },
        ],
      });
    final list = await _repo(client).officialTracking();
    expect(list.first.affectedCaseCount, 3);
    expect(list.first.newVersionDetected, isTrue);
  });
}
