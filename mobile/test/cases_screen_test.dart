import 'package:emsalist_mobile/features/cases/application/case_providers.dart';
import 'package:emsalist_mobile/features/cases/data/case_api.dart';
import 'package:emsalist_mobile/features/cases/data/case_repository.dart';
import 'package:emsalist_mobile/features/cases/presentation/cases_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_api_client.dart';

Widget _host(FakeApiClient client) {
  return ProviderScope(
    overrides: <Override>[
      caseRepositoryProvider.overrideWithValue(CaseRepository(CaseApi(client))),
    ],
    child: const MaterialApp(home: CasesScreen()),
  );
}

void main() {
  testWidgets('shows loading then empty state when no cases', (
    WidgetTester tester,
  ) async {
    final FakeApiClient client = FakeApiClient()
      ..whenGet(CaseApi.casesPath, <String, dynamic>{
        'items': <dynamic>[],
        'total': 0,
        'has_more': false,
      });

    await tester.pumpWidget(_host(client));
    await tester.pump(); // start futures
    await tester.pumpAndSettle();

    expect(find.text('Henüz dosya yok'), findsOneWidget);
    expect(find.text('Yeni Dosya'), findsOneWidget);
  });

  testWidgets('renders active cases', (WidgetTester tester) async {
    final FakeApiClient client = FakeApiClient()
      ..whenGetWithQuery(
        CaseApi.casesPath,
        'archived',
        false,
        <String, dynamic>{
          'items': <dynamic>[
            <String, dynamic>{
              'id': 'c1',
              'title': 'Araç Ayıbı',
              'legal_topic': 'Tüketici',
              'status': 'active',
              'version': 1,
            },
          ],
          'total': 1,
          'has_more': false,
        },
      )
      ..whenGetWithQuery(CaseApi.casesPath, 'archived', true, <String, dynamic>{
        'items': <dynamic>[],
        'total': 0,
        'has_more': false,
      });

    await tester.pumpWidget(_host(client));
    await tester.pumpAndSettle();

    expect(find.text('Araç Ayıbı'), findsOneWidget);
    expect(find.text('Aktif Dosyalar'), findsOneWidget);
    expect(find.byIcon(Icons.archive_outlined), findsOneWidget);
  });

  testWidgets('shows error state with retry on failure', (
    WidgetTester tester,
  ) async {
    final FakeApiClient client = FakeApiClient()
      ..whenGetError(CaseApi.casesPath, StateError('boom'));

    await tester.pumpWidget(_host(client));
    await tester.pumpAndSettle();

    expect(find.text('Tekrar Dene'), findsOneWidget);
  });
}
