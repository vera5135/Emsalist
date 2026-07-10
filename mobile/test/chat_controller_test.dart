import 'package:emsalist_mobile/features/cases/application/chat_controller.dart';
import 'package:emsalist_mobile/features/cases/data/case_api.dart';
import 'package:emsalist_mobile/features/cases/data/case_repository.dart';
import 'package:emsalist_mobile/core/network/api_exception.dart';
import 'package:emsalist_mobile/features/cases/domain/chat_message.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_api_client.dart';

const String _caseId = 'c1';
const String _convPath = '/api/v1/cases/$_caseId/conversations';
const String _messagesPath = '/api/v1/conversations/conv1/messages';

FakeApiClient _clientWithConversation({
  List<Map<String, dynamic>> initialMessages = const <Map<String, dynamic>>[],
  int total = 0,
  bool hasMore = false,
}) {
  return FakeApiClient()
    ..whenPost(_convPath, <String, dynamic>{
      'id': 'conv1',
      'case_id': _caseId,
      'title': '',
      'status': 'active',
    })
    ..whenGet(_messagesPath, <String, dynamic>{
      'items': initialMessages,
      'total': total,
      'has_more': hasMore,
    });
}

Future<ChatController> _bootstrapped(FakeApiClient client) async {
  final ChatController controller = ChatController(
    repository: CaseRepository(CaseApi(client)),
    caseId: _caseId,
  );
  // Allow the async _init() to complete.
  await Future<void>.delayed(Duration.zero);
  await Future<void>.delayed(Duration.zero);
  return controller;
}

void main() {
  test('initial load resolves conversation and messages', () async {
    final FakeApiClient client = _clientWithConversation(
      initialMessages: <Map<String, dynamic>>[
        <String, dynamic>{
          'id': 'm1',
          'conversation_id': 'conv1',
          'case_id': _caseId,
          'role': 'user',
          'content': 'eski',
          'status': 'completed',
          'client_request_id': 'r0',
        },
      ],
      total: 1,
    );
    final ChatController controller = await _bootstrapped(client);

    expect(controller.state.loading, isFalse);
    expect(controller.state.conversationId, 'conv1');
    expect(controller.state.messages, hasLength(1));
  });

  test('sendMessage appends optimistic then marks sent', () async {
    final FakeApiClient client = _clientWithConversation()
      ..whenPost(_messagesPath, <String, dynamic>{
        'id': 'm-server',
        'conversation_id': 'conv1',
        'case_id': _caseId,
        'role': 'user',
        'content': 'merhaba',
        'status': 'completed',
        'client_request_id': 'ignored',
      });
    final ChatController controller = await _bootstrapped(client);

    await controller.sendMessage('merhaba');

    expect(controller.state.messages, hasLength(1));
    expect(controller.state.messages.single.content, 'merhaba');
    expect(controller.state.messages.single.status, ChatMessageStatus.sent);
    expect(controller.state.messages.single.id, 'm-server');
  });

  test('failed send marks message failed and retry succeeds', () async {
    final FakeApiClient client = _clientWithConversation()
      ..whenPostError(
        _messagesPath,
        const ApiException(kind: ApiErrorKind.network, message: 'offline'),
      );
    final ChatController controller = await _bootstrapped(client);

    await controller.sendMessage('kayıp');
    expect(controller.state.messages.single.status, ChatMessageStatus.failed);
    final String crid = controller.state.messages.single.clientRequestId;

    // Recover: server now accepts.
    client.whenPost(_messagesPath, <String, dynamic>{
      'id': 'm-recovered',
      'conversation_id': 'conv1',
      'case_id': _caseId,
      'role': 'user',
      'content': 'kayıp',
      'status': 'completed',
      'client_request_id': crid,
    });
    await controller.retryMessage(crid);

    expect(controller.state.messages, hasLength(1));
    expect(controller.state.messages.single.status, ChatMessageStatus.sent);
    expect(controller.state.messages.single.id, 'm-recovered');
  });

  test('initial load error is surfaced and retryable', () async {
    final FakeApiClient client = FakeApiClient()
      ..whenPostError(
        _convPath,
        const ApiException(kind: ApiErrorKind.server, message: 'boom'),
      );
    final ChatController controller = await _bootstrapped(client);

    expect(controller.state.loading, isFalse);
    expect(controller.state.error, isNotNull);
    expect(controller.state.messages, isEmpty);
  });

  test('loadMore prepends older messages', () async {
    final FakeApiClient client = _clientWithConversation(
      initialMessages: <Map<String, dynamic>>[
        <String, dynamic>{
          'id': 'm2',
          'conversation_id': 'conv1',
          'case_id': _caseId,
          'role': 'user',
          'content': 'newer',
          'status': 'completed',
          'client_request_id': 'r2',
        },
      ],
      total: 2,
      hasMore: true,
    );
    final ChatController controller = await _bootstrapped(client);
    expect(controller.state.hasMore, isTrue);

    // Next page returns the older message; has_more now false.
    client.whenGet(_messagesPath, <String, dynamic>{
      'items': <dynamic>[
        <String, dynamic>{
          'id': 'm1',
          'conversation_id': 'conv1',
          'case_id': _caseId,
          'role': 'user',
          'content': 'older',
          'status': 'completed',
          'client_request_id': 'r1',
        },
      ],
      'total': 2,
      'has_more': false,
    });
    await controller.loadMore();

    expect(
      controller.state.messages.map((ChatMessage m) => m.content).toList(),
      <String>['older', 'newer'],
    );
    expect(controller.state.hasMore, isFalse);
  });
}
