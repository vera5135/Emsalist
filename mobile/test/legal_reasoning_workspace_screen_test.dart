import 'package:emsalist_mobile/core/network/api_exception.dart';
import 'package:emsalist_mobile/features/legal_reasoning/application/legal_reasoning_providers.dart';
import 'package:emsalist_mobile/features/legal_reasoning/data/legal_reasoning_repository.dart';
import 'package:emsalist_mobile/features/legal_reasoning/presentation/legal_reasoning_workspace_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_api_client.dart';

const String _caseId = 'case-1';
const String _issuesPath = '/api/v1/cases/$_caseId/legal-issues';
const String _graphPath = '/api/v1/legal-issues/root/graph';
const String _rebuildPath = '/api/v1/cases/$_caseId/legal-issues/rebuild';

Widget _host(FakeApiClient client) => ProviderScope(
  overrides: <Override>[
    legalReasoningRepositoryProvider.overrideWithValue(
      LegalReasoningRepository(client),
    ),
  ],
  child: const MaterialApp(
    home: LegalReasoningWorkspaceScreen(caseId: _caseId),
  ),
);

List<dynamic> _issues({bool stale = false}) => <dynamic>[
  <String, dynamic>{
    'id': 'root',
    'parent_issue_id': null,
    'title': 'Ayıplı araç sorumluluğu',
    'description': 'Satıcının hukuki sorumluluğu',
    'status': 'identified',
    'support_state': 'partial',
    'stale': stale,
    'version': 1,
  },
  <String, dynamic>{
    'id': 'child',
    'parent_issue_id': 'root',
    'title': 'Ayıbın varlığı',
    'status': 'needs_review',
    'support_state': 'strong',
    'stale': stale,
    'version': 1,
  },
];

Map<String, dynamic> _graph({bool stale = false}) => <String, dynamic>{
  'case_id': _caseId,
  'stale': stale,
  'issues': <dynamic>[],
  'burdens': <dynamic>[
    <String, dynamic>{
      'issue_id': 'root',
      'burden_type': 'ispat',
      'evidence_status': 'review_required',
    },
  ],
  'counterarguments': <dynamic>[
    <String, dynamic>{
      'issue_id': 'root',
      'title': 'Alternatif olgu yorumu',
      'rationale': 'Arıza kullanıcı kullanımından doğmuş olabilir.',
    },
  ],
  'source_links': <dynamic>[
    <String, dynamic>{
      'issue_id': 'root',
      'source_record_id': 'record-1',
      'source_version_id': 'version-2',
      'source_paragraph_id': 'paragraph-3',
    },
  ],
  'evidence_links': <dynamic>[],
  'missing_information': <dynamic>[],
  'unsupported_claims': <dynamic>[],
};

void main() {
  testWidgets(
    'shows hierarchy, support, counterargument, burden and source provenance',
    (WidgetTester tester) async {
      final FakeApiClient client = FakeApiClient()
        ..whenGetRaw(_issuesPath, _issues())
        ..whenGet(_graphPath, _graph());

      await tester.pumpWidget(_host(client));
      await tester.pumpAndSettle();

      expect(find.text('Ayıplı araç sorumluluğu'), findsOneWidget);
      expect(find.text('Ayıbın varlığı'), findsOneWidget);
      expect(find.text('Kısmi destek'), findsOneWidget);
      expect(find.text('İspat yükü'), findsOneWidget);
      expect(find.text('Alternatif olgu yorumu'), findsOneWidget);
      expect(find.text('record-1 / version-2 / paragraph-3'), findsOneWidget);
    },
  );

  testWidgets('shows stale warning', (WidgetTester tester) async {
    final FakeApiClient client = FakeApiClient()
      ..whenGetRaw(_issuesPath, _issues(stale: true))
      ..whenGet(_graphPath, _graph(stale: true));
    await tester.pumpWidget(_host(client));
    await tester.pumpAndSettle();
    expect(find.text('Analiz güncel değil'), findsOneWidget);
  });

  testWidgets('empty graph can be rebuilt and refetched', (
    WidgetTester tester,
  ) async {
    final FakeApiClient client = FakeApiClient()
      ..whenGetRaw(_issuesPath, <dynamic>[])
      ..whenPost(_rebuildPath, <String, dynamic>{'status': 'succeeded'});
    await tester.pumpWidget(_host(client));
    await tester.pumpAndSettle();
    expect(find.text('Henüz hukuki konu yok'), findsOneWidget);
    await tester.tap(find.text('Oluştur'));
    await tester.pumpAndSettle();
    expect(client.postPaths, contains(_rebuildPath));
    expect(client.getPaths.where((path) => path == _issuesPath).length, 2);
  });

  testWidgets('renders safe error state', (WidgetTester tester) async {
    final FakeApiClient client = FakeApiClient()
      ..whenGetError(
        _issuesPath,
        const ApiException(
          kind: ApiErrorKind.network,
          message: 'Bağlantı kurulamadı.',
        ),
      );
    await tester.pumpWidget(_host(client));
    await tester.pumpAndSettle();
    expect(find.text('Bağlantı kurulamadı.'), findsOneWidget);
    expect(find.text('Tekrar Dene'), findsOneWidget);
  });
}
