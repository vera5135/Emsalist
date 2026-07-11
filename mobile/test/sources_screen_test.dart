import 'package:emsalist_mobile/features/sources/application/source_providers.dart';
import 'package:emsalist_mobile/features/sources/data/source_api.dart';
import 'package:emsalist_mobile/features/sources/data/source_repository.dart';
import 'package:emsalist_mobile/features/sources/presentation/sources_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_api_client.dart';

const String _caseId = 'c1';

Widget _host(FakeApiClient client, {Widget? home}) {
  return ProviderScope(
    overrides: <Override>[
      sourceRepositoryProvider.overrideWithValue(
        SourceRepository(SourceApi(client)),
      ),
    ],
    child: MaterialApp(home: home ?? const SourcesScreen()),
  );
}

Map<String, dynamic> _record({String status = 'verified_official'}) {
  return <String, dynamic>{
    'id': 's1',
    'source_type': 'supreme_court_decision',
    'title': 'Yargıtay 13. HD',
    'court': 'Yargıtay',
    'chamber': '13. HD',
    'case_number': '2020/123',
    'decision_number': '2021/456',
    'decision_date': '2021-06-12',
    'official_url': 'https://karararama.yargitay.gov.tr/x',
    'verification_status': status,
    'temporal_status': 'valid',
    'current_version_id': 'v1',
    'version': 1,
  };
}

void main() {
  testWidgets('sources list empty state', (WidgetTester tester) async {
    final FakeApiClient client = FakeApiClient()
      ..whenGet(SourceApi.sourcesPath, <String, dynamic>{
        'items': <dynamic>[],
        'total': 0,
        'has_more': false,
      });
    await tester.pumpWidget(_host(client));
    await tester.pumpAndSettle();
    expect(find.text('Henüz kaynak yok'), findsOneWidget);
  });

  testWidgets('sources list error + retry', (WidgetTester tester) async {
    final FakeApiClient client = FakeApiClient()
      ..whenGetError(SourceApi.sourcesPath, StateError('boom'));
    await tester.pumpWidget(_host(client));
    await tester.pumpAndSettle();
    expect(find.text('Tekrar Dene'), findsOneWidget);
  });

  testWidgets('official verified card shows user-facing badge', (
    WidgetTester tester,
  ) async {
    final FakeApiClient client = FakeApiClient()
      ..whenGet(SourceApi.sourcesPath, <String, dynamic>{
        'items': <dynamic>[_record()],
        'total': 1,
        'has_more': false,
      });
    await tester.pumpWidget(_host(client));
    await tester.pumpAndSettle();
    expect(find.text('Yargıtay 13. HD'), findsOneWidget);
    expect(find.text('Resmî kaynaktan doğrulandı'), findsOneWidget);
  });

  testWidgets('conflicting card shows conflicting label, no snake_case', (
    WidgetTester tester,
  ) async {
    final FakeApiClient client = FakeApiClient()
      ..whenGet(SourceApi.sourcesPath, <String, dynamic>{
        'items': <dynamic>[_record(status: 'conflicting')],
        'total': 1,
        'has_more': false,
      });
    await tester.pumpWidget(_host(client));
    await tester.pumpAndSettle();
    expect(find.text('Çelişkili kaynak'), findsOneWidget);
    expect(find.textContaining('conflicting'), findsNothing);
  });

  testWidgets('official tracking screen renders affected case count', (
    WidgetTester tester,
  ) async {
    final FakeApiClient client = FakeApiClient()
      ..whenGet(SourceApi.trackingPath, <String, dynamic>{
        'items': <dynamic>[
          <String, dynamic>{
            'source_id': 's1',
            'title': 'Türk Borçlar Kanunu',
            'source_type': 'legislation',
            'affected_case_count': 2,
            'new_version_detected': true,
            'requires_review': true,
            'last_successful_check_at': '2026-01-01T00:00:00Z',
          },
        ],
      });
    await tester.pumpWidget(
      _host(client, home: const OfficialTrackingScreen()),
    );
    await tester.pumpAndSettle();
    expect(find.text('Türk Borçlar Kanunu'), findsOneWidget);
    expect(find.text('Yeni sürüm mevcut'), findsOneWidget);
    expect(find.text('Etkilenen dosya: 2'), findsOneWidget);
    expect(find.text('Yeniden inceleme gerekli'), findsOneWidget);
  });

  testWidgets('case sources list shows usage without fake draft flag', (
    WidgetTester tester,
  ) async {
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
            'reason': 'İade dayanağı',
            'selected_paragraph': 'İlgili paragraf metni',
          },
        ],
      });
    await tester.pumpWidget(
      _host(client, home: const CaseSourcesScreen(caseId: _caseId)),
    );
    await tester.pumpAndSettle();
    expect(find.text('Yargıtay 13. HD'), findsOneWidget);
    expect(find.textContaining('İade dayanağı'), findsOneWidget);
    // Draft usage is only shown when truly used; here it must be absent.
    expect(find.text('Dilekçede kullanıldı'), findsNothing);
  });

  testWidgets('case sources empty state', (WidgetTester tester) async {
    final FakeApiClient client = FakeApiClient()
      ..whenGet('/api/v1/cases/$_caseId/sources', <String, dynamic>{
        'items': <dynamic>[],
      });
    await tester.pumpWidget(
      _host(client, home: const CaseSourcesScreen(caseId: _caseId)),
    );
    await tester.pumpAndSettle();
    expect(find.text('Bu dosyada kaynak yok'), findsOneWidget);
  });
}
