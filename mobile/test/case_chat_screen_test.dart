import 'package:emsalist_mobile/features/cases/application/case_providers.dart';
import 'package:emsalist_mobile/features/cases/data/case_api.dart';
import 'package:emsalist_mobile/features/cases/data/case_repository.dart';
import 'package:emsalist_mobile/features/cases/presentation/case_chat_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_api_client.dart';

const String _caseId = 'c1';
const String _convPath = '/api/v1/cases/$_caseId/conversations';
const String _casePath = '/api/v1/cases/$_caseId';
const String _messagesPath = '/api/v1/conversations/conv1/messages';

Widget _host(FakeApiClient client) {
  return ProviderScope(
    overrides: <Override>[
      caseRepositoryProvider.overrideWithValue(CaseRepository(CaseApi(client))),
    ],
    child: const MaterialApp(home: CaseChatScreen(caseId: _caseId)),
  );
}

FakeApiClient _client({
  List<Map<String, dynamic>> messages = const <Map<String, dynamic>>[],
}) {
  return FakeApiClient()
    ..whenGet(_casePath, <String, dynamic>{
      'id': _caseId,
      'title': 'Araç Ayıbı',
      'legal_topic': 'Tüketici',
      'status': 'active',
      'version': 1,
    })
    ..whenPost(_convPath, <String, dynamic>{
      'id': 'conv1',
      'case_id': _caseId,
      'title': '',
      'status': 'active',
    })
    ..whenGet(_messagesPath, <String, dynamic>{
      'items': messages,
      'total': messages.length,
      'has_more': false,
    });
}

void main() {
  testWidgets('empty conversation shows empty state and case title', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(_host(_client()));
    await tester.pumpAndSettle();

    expect(find.text('Araç Ayıbı'), findsOneWidget);
    expect(find.text('Sohbet boş'), findsOneWidget);
  });

  testWidgets('renders existing messages', (WidgetTester tester) async {
    await tester.pumpWidget(
      _host(
        _client(
          messages: <Map<String, dynamic>>[
            <String, dynamic>{
              'id': 'm1',
              'conversation_id': 'conv1',
              'case_id': _caseId,
              'role': 'user',
              'content': 'Merhaba',
              'status': 'completed',
              'client_request_id': 'r1',
            },
          ],
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Merhaba'), findsOneWidget);
  });

  testWidgets('sending a message shows it optimistically then sent', (
    WidgetTester tester,
  ) async {
    final FakeApiClient client = _client()
      ..whenPost(_messagesPath, <String, dynamic>{
        'id': 'm-server',
        'conversation_id': 'conv1',
        'case_id': _caseId,
        'role': 'user',
        'content': 'Yeni mesaj',
        'status': 'completed',
        'client_request_id': 'x',
      });

    await tester.pumpWidget(_host(client));
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(TextField), 'Yeni mesaj');
    await tester.pump();
    await tester.tap(find.byIcon(Icons.send));
    await tester.pumpAndSettle();

    expect(find.text('Yeni mesaj'), findsOneWidget);
    expect(find.text('Gönderildi'), findsOneWidget);
  });

  testWidgets('failed send surfaces retry affordance', (
    WidgetTester tester,
  ) async {
    final FakeApiClient client = _client()
      ..whenPostError(_messagesPath, StateError('offline'));

    await tester.pumpWidget(_host(client));
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(TextField), 'Kayıp mesaj');
    await tester.pump();
    await tester.tap(find.byIcon(Icons.send));
    await tester.pumpAndSettle();

    expect(find.text('Gönderilemedi'), findsOneWidget);
    expect(find.text('Yeniden dene'), findsOneWidget);
  });
}
