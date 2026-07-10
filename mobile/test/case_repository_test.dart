import 'package:emsalist_mobile/features/cases/data/case_api.dart';
import 'package:emsalist_mobile/features/cases/data/case_repository.dart';
import 'package:emsalist_mobile/features/cases/domain/chat_message.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_api_client.dart';

CaseRepository _repo(FakeApiClient client) => CaseRepository(CaseApi(client));

void main() {
  group('CaseRepository — cases', () {
    test('listCases maps items', () async {
      final FakeApiClient client = FakeApiClient()
        ..whenGet(CaseApi.casesPath, <String, dynamic>{
          'items': <dynamic>[
            <String, dynamic>{
              'id': 'c1',
              'title': 'Araç',
              'legal_topic': 'Tüketici',
              'status': 'active',
              'version': 1,
            },
          ],
          'total': 1,
          'has_more': false,
        });

      final cases = await _repo(client).listCases();

      expect(cases, hasLength(1));
      expect(cases.first.id, 'c1');
      expect(cases.first.title, 'Araç');
      expect(cases.first.isActive, isTrue);
    });

    test('createCase returns the created case', () async {
      final FakeApiClient client = FakeApiClient()
        ..whenPost(CaseApi.casesPath, <String, dynamic>{
          'id': 'c2',
          'title': 'Yeni',
          'legal_topic': '',
          'status': 'active',
          'version': 1,
        });

      final created = await _repo(client).createCase(title: 'Yeni');

      expect(created.id, 'c2');
      expect(client.postPaths, contains(CaseApi.casesPath));
    });

    test('archiveCase hits the archive endpoint', () async {
      final FakeApiClient client = FakeApiClient()
        ..whenPost('${CaseApi.casesPath}/c1/archive', <String, dynamic>{
          'id': 'c1',
          'title': 'A',
          'status': 'archived',
          'version': 2,
        });

      final archived = await _repo(client).archiveCase('c1');

      expect(archived.isArchived, isTrue);
    });

    test('displayTitle falls back for empty title', () async {
      final FakeApiClient client = FakeApiClient()
        ..whenGet('${CaseApi.casesPath}/c9', <String, dynamic>{
          'id': 'c9',
          'title': '',
          'status': 'active',
          'version': 1,
        });
      final item = await _repo(client).getCase('c9');
      expect(item.displayTitle, 'İsimsiz dosya');
    });
  });

  group('CaseRepository — conversations & messages', () {
    test('conversationIdForCase returns id', () async {
      final FakeApiClient client = FakeApiClient()
        ..whenPost('${CaseApi.casesPath}/c1/conversations', <String, dynamic>{
          'id': 'conv1',
          'case_id': 'c1',
          'title': '',
          'status': 'active',
        });
      expect(await _repo(client).conversationIdForCase('c1'), 'conv1');
    });

    test('loadMessages maps to domain and pagination flags', () async {
      final FakeApiClient client = FakeApiClient()
        ..whenGet('/api/v1/conversations/conv1/messages', <String, dynamic>{
          'items': <dynamic>[
            <String, dynamic>{
              'id': 'm1',
              'conversation_id': 'conv1',
              'case_id': 'c1',
              'role': 'user',
              'content': 'hi',
              'status': 'completed',
              'client_request_id': 'r1',
            },
          ],
          'total': 5,
          'has_more': true,
        });

      final page = await _repo(client).loadMessages('conv1');

      expect(page.messages, hasLength(1));
      expect(page.messages.first.content, 'hi');
      expect(page.messages.first.status, ChatMessageStatus.sent);
      expect(page.hasMore, isTrue);
      expect(page.total, 5);
    });

    test('sendMessage forwards content + client_request_id', () async {
      final FakeApiClient client = FakeApiClient()
        ..whenPost('/api/v1/conversations/conv1/messages', <String, dynamic>{
          'id': 'm2',
          'conversation_id': 'conv1',
          'case_id': 'c1',
          'role': 'user',
          'content': 'hello',
          'status': 'completed',
          'client_request_id': 'req-1',
        });

      final saved = await _repo(
        client,
      ).sendMessage('conv1', content: 'hello', clientRequestId: 'req-1');

      expect(saved.id, 'm2');
      expect(saved.status, ChatMessageStatus.sent);
      final Object? body = client.postBodies.first;
      expect((body! as Map<String, dynamic>)['content'], 'hello');
      expect((body as Map<String, dynamic>)['client_request_id'], 'req-1');
    });
  });
}
