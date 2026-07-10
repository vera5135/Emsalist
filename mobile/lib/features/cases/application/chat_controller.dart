import 'dart:math';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/case_repository.dart';
import '../domain/chat_message.dart';
import 'case_providers.dart';

/// Immutable chat state for a single case's conversation.
class ChatState {
  const ChatState({
    this.loading = true,
    this.loadingMore = false,
    this.error,
    this.conversationId,
    this.messages = const <ChatMessage>[],
    this.hasMore = false,
    this.total = 0,
  });

  final bool loading;
  final bool loadingMore;
  final Object? error;
  final String? conversationId;

  /// Newest-last ordering (matches backend created_at ascending).
  final List<ChatMessage> messages;
  final bool hasMore;
  final int total;

  ChatState copyWith({
    bool? loading,
    bool? loadingMore,
    Object? error,
    bool clearError = false,
    String? conversationId,
    List<ChatMessage>? messages,
    bool? hasMore,
    int? total,
  }) {
    return ChatState(
      loading: loading ?? this.loading,
      loadingMore: loadingMore ?? this.loadingMore,
      error: clearError ? null : (error ?? this.error),
      conversationId: conversationId ?? this.conversationId,
      messages: messages ?? this.messages,
      hasMore: hasMore ?? this.hasMore,
      total: total ?? this.total,
    );
  }
}

/// Owns the message list for one case: initial load, pagination, optimistic
/// send with sending→sent/failed, and retry of failed messages.
class ChatController extends StateNotifier<ChatState> {
  ChatController({required CaseRepository repository, required this.caseId})
    : _repository = repository,
      super(const ChatState()) {
    _init();
  }

  final CaseRepository _repository;
  final String caseId;

  static const int _pageSize = 30;

  Future<void> _init() async {
    state = const ChatState(loading: true);
    try {
      final String conversationId = await _repository.conversationIdForCase(
        caseId,
      );
      final MessagePage page = await _repository.loadMessages(
        conversationId,
        limit: _pageSize,
        offset: 0,
      );
      state = ChatState(
        loading: false,
        conversationId: conversationId,
        messages: page.messages,
        hasMore: page.hasMore,
        total: page.total,
      );
    } on Object catch (error) {
      state = ChatState(loading: false, error: error);
    }
  }

  Future<void> retryInitialLoad() => _init();

  /// Loads an older page (prepends earlier messages).
  Future<void> loadMore() async {
    final String? conversationId = state.conversationId;
    if (conversationId == null || state.loadingMore || !state.hasMore) {
      return;
    }
    state = state.copyWith(loadingMore: true, clearError: true);
    try {
      final MessagePage page = await _repository.loadMessages(
        conversationId,
        limit: _pageSize,
        offset: state.messages.length,
      );
      state = state.copyWith(
        loadingMore: false,
        messages: <ChatMessage>[...page.messages, ...state.messages],
        hasMore: page.hasMore,
        total: page.total,
      );
    } on Object catch (error) {
      state = state.copyWith(loadingMore: false, error: error);
    }
  }

  String _newClientRequestId() {
    final int now = DateTime.now().microsecondsSinceEpoch;
    final int salt = Random().nextInt(0x7fffffff);
    return 'm-$now-$salt';
  }

  /// Optimistically appends the user message then confirms with the server.
  Future<void> sendMessage(String rawContent) async {
    final String content = rawContent.trim();
    final String? conversationId = state.conversationId;
    if (content.isEmpty || conversationId == null) {
      return;
    }
    final String clientRequestId = _newClientRequestId();
    final ChatMessage optimistic = ChatMessage(
      id: 'local-$clientRequestId',
      role: ChatMessageRole.user,
      content: content,
      status: ChatMessageStatus.sending,
      clientRequestId: clientRequestId,
      createdAt: DateTime.now(),
    );
    state = state.copyWith(
      messages: <ChatMessage>[...state.messages, optimistic],
    );
    await _deliver(optimistic);
  }

  /// Retries a previously failed message (reuses its client_request_id so the
  /// backend idempotently returns the original if it did persist).
  Future<void> retryMessage(String clientRequestId) async {
    final int index = state.messages.indexWhere(
      (ChatMessage m) => m.clientRequestId == clientRequestId,
    );
    if (index < 0) {
      return;
    }
    final ChatMessage failed = state.messages[index];
    if (!failed.isFailed) {
      return;
    }
    final List<ChatMessage> updated = <ChatMessage>[...state.messages];
    updated[index] = failed.copyWith(status: ChatMessageStatus.sending);
    state = state.copyWith(messages: updated);
    await _deliver(updated[index]);
  }

  Future<void> _deliver(ChatMessage optimistic) async {
    final String? conversationId = state.conversationId;
    if (conversationId == null) {
      return;
    }
    try {
      final ChatMessage saved = await _repository.sendMessage(
        conversationId,
        content: optimistic.content,
        clientRequestId: optimistic.clientRequestId,
      );
      _replaceByClientRequestId(optimistic.clientRequestId, saved);
    } on Object {
      _replaceByClientRequestId(
        optimistic.clientRequestId,
        optimistic.copyWith(status: ChatMessageStatus.failed),
      );
    }
  }

  void _replaceByClientRequestId(
    String clientRequestId,
    ChatMessage replacement,
  ) {
    final List<ChatMessage> updated = state.messages
        .map(
          (ChatMessage m) =>
              m.clientRequestId == clientRequestId ? replacement : m,
        )
        .toList();
    state = state.copyWith(messages: updated);
  }
}

/// One [ChatController] per case id.
final StateNotifierProviderFamily<ChatController, ChatState, String>
chatControllerProvider =
    StateNotifierProvider.family<ChatController, ChatState, String>((
      ref,
      String caseId,
    ) {
      return ChatController(
        repository: ref.watch(caseRepositoryProvider),
        caseId: caseId,
      );
    });
