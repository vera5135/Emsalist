import 'package:emsalist_mobile/features/case_memory/application/case_memory_providers.dart';
import 'package:emsalist_mobile/features/case_memory/data/case_memory_api.dart';
import 'package:emsalist_mobile/features/case_memory/data/case_memory_repository.dart';
import 'package:emsalist_mobile/features/case_memory/presentation/case_memory_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_api_client.dart';

const String _caseId = 'c1';
const String _base = '/api/v1/cases/$_caseId/memory';

Widget _host(FakeApiClient client) {
  return ProviderScope(
    overrides: <Override>[
      caseMemoryRepositoryProvider.overrideWithValue(
        CaseMemoryRepository(CaseMemoryApi(client)),
      ),
    ],
    child: const MaterialApp(home: CaseMemoryScreen(caseId: _caseId)),
  );
}

Map<String, dynamic> _memory({
  String overall = 'low',
  List<Map<String, dynamic>> facts = const <Map<String, dynamic>>[],
  List<Map<String, dynamic>> missing = const <Map<String, dynamic>>[],
  List<Map<String, dynamic>> contradictions = const <Map<String, dynamic>>[],
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

void main() {
  testWidgets('renders overall risk summary', (WidgetTester tester) async {
    final FakeApiClient client = FakeApiClient()
      ..whenGet(_base, _memory(overall: 'high'));

    await tester.pumpWidget(_host(client));
    await tester.pumpAndSettle();

    expect(find.text('Dosya Hafızası'), findsOneWidget);
    expect(find.textContaining('Genel Risk'), findsOneWidget);
    expect(find.text('Yüksek'), findsWidgets);
  });

  testWidgets('shows error state with retry on failure', (
    WidgetTester tester,
  ) async {
    final FakeApiClient client = FakeApiClient()
      ..whenGetError(_base, StateError('boom'));

    await tester.pumpWidget(_host(client));
    await tester.pumpAndSettle();

    expect(find.text('Tekrar Dene'), findsOneWidget);
  });

  testWidgets('facts tab renders fact and verification badge', (
    WidgetTester tester,
  ) async {
    final FakeApiClient client = FakeApiClient()
      ..whenGet(
        _base,
        _memory(
          facts: <Map<String, dynamic>>[
            <String, dynamic>{
              'id': 'f1',
              'case_id': _caseId,
              'fact_type': 'sale_amount',
              'value': '150000',
              'verification_status': 'suggested',
              'source_type': 'user_message',
              'version': 1,
            },
          ],
        ),
      );

    await tester.pumpWidget(_host(client));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Olaylar'));
    await tester.pumpAndSettle();

    expect(find.text('150000'), findsOneWidget);
    expect(find.text('Önerildi'), findsWidgets);
  });

  testWidgets('confirm action calls repository and refetches', (
    WidgetTester tester,
  ) async {
    final FakeApiClient client = FakeApiClient()
      ..whenGet(
        _base,
        _memory(
          facts: <Map<String, dynamic>>[
            <String, dynamic>{
              'id': 'f1',
              'case_id': _caseId,
              'fact_type': 'x',
              'value': 'v',
              'verification_status': 'suggested',
              'version': 1,
            },
          ],
        ),
      )
      ..whenPost('$_base/facts/f1/confirm', <String, dynamic>{
        'id': 'f1',
        'case_id': _caseId,
        'fact_type': 'x',
        'value': 'v',
        'verification_status': 'user_confirmed',
        'version': 2,
      });

    await tester.pumpWidget(_host(client));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Olaylar'));
    await tester.pumpAndSettle();

    await tester.tap(find.byType(PopupMenuButton<String>).first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Doğrula'));
    await tester.pumpAndSettle();

    expect(client.postPaths, contains('$_base/facts/f1/confirm'));
  });

  testWidgets('missing tab shows open item with complete action', (
    WidgetTester tester,
  ) async {
    final FakeApiClient client = FakeApiClient()
      ..whenGet(
        _base,
        _memory(
          missing: <Map<String, dynamic>>[
            <String, dynamic>{
              'id': 'm1',
              'case_id': _caseId,
              'field_key': 'sale_amount',
              'label': 'Satış bedeli',
              'importance': 'critical',
              'status': 'open',
            },
          ],
        ),
      );

    await tester.pumpWidget(_host(client));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Eksikler'));
    await tester.pumpAndSettle();

    expect(find.text('Satış bedeli'), findsOneWidget);
    expect(find.text('Tamamla'), findsOneWidget);
  });

  testWidgets('contradictions tab shows open contradiction with resolve', (
    WidgetTester tester,
  ) async {
    final FakeApiClient client = FakeApiClient()
      ..whenGet(
        _base,
        _memory(
          contradictions: <Map<String, dynamic>>[
            <String, dynamic>{
              'id': 'x1',
              'case_id': _caseId,
              'contradiction_type': 'value_mismatch',
              'description': 'Farklı plaka',
              'fact_ids': <String>['f1', 'f2'],
              'severity': 'high',
              'status': 'open',
            },
          ],
        ),
      );

    await tester.pumpWidget(_host(client));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Çelişkiler'));
    await tester.pumpAndSettle();

    expect(find.text('Farklı plaka'), findsOneWidget);
    expect(find.text('Çöz'), findsOneWidget);
  });

  testWidgets('risks tab renders risk', (WidgetTester tester) async {
    final FakeApiClient client = FakeApiClient()
      ..whenGet(
        _base,
        _memory(
          risks: <Map<String, dynamic>>[
            <String, dynamic>{
              'id': 'r1',
              'case_id': _caseId,
              'risk_type': 'deadline',
              'severity': 'high',
              'title': 'Hak düşürücü süre',
              'rationale': 'İhbar süresi',
              'status': 'open',
            },
          ],
        ),
      );

    await tester.pumpWidget(_host(client));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Riskler'));
    await tester.pumpAndSettle();

    expect(find.text('Hak düşürücü süre'), findsOneWidget);
  });

  testWidgets('empty memory shows empty facts state', (
    WidgetTester tester,
  ) async {
    final FakeApiClient client = FakeApiClient()..whenGet(_base, _memory());

    await tester.pumpWidget(_host(client));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Olaylar'));
    await tester.pumpAndSettle();

    expect(find.text('Henüz bilgi yok'), findsOneWidget);
  });
}
