import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../app/app_router.dart';
import '../../../core/constants/app_constants.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/widgets/state_widgets.dart';
import '../../../design_system/components/emsalist_composer.dart';
import '../application/case_providers.dart';
import '../application/chat_controller.dart';
import '../domain/case_item.dart';
import '../domain/chat_message.dart';

/// Case-based chat screen: message list, send with delivery status, retry,
/// pagination (load older), and keyboard/small-screen friendly layout.
class CaseChatScreen extends ConsumerWidget {
  const CaseChatScreen({required this.caseId, super.key});

  final String caseId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final ChatState chat = ref.watch(chatControllerProvider(caseId));
    final ChatController controller = ref.read(
      chatControllerProvider(caseId).notifier,
    );
    final AsyncValue<CaseItem> detail = ref.watch(caseDetailProvider(caseId));

    final String title = detail.maybeWhen(
      data: (CaseItem c) => c.displayTitle,
      orElse: () => 'Sohbet',
    );

    return Scaffold(
      appBar: AppBar(
        title: Text(title),
        actions: <Widget>[
          IconButton(
            icon: const Icon(Icons.account_tree_outlined),
            tooltip: 'Hukuki Konular',
            onPressed: () => context.pushNamed(
              AppRoutes.caseLegalIssues,
              pathParameters: <String, String>{'caseId': caseId},
            ),
          ),
          IconButton(
            icon: const Icon(Icons.folder_outlined),
            tooltip: 'Belgeler',
            onPressed: () => context.pushNamed(
              AppRoutes.caseDocuments,
              pathParameters: <String, String>{'caseId': caseId},
            ),
          ),
          IconButton(
            icon: const Icon(Icons.menu_book_outlined),
            tooltip: 'Kaynaklar',
            onPressed: () => context.pushNamed(
              AppRoutes.caseSources,
              pathParameters: <String, String>{'caseId': caseId},
            ),
          ),
          IconButton(
            icon: const Icon(Icons.psychology_outlined),
            tooltip: 'Dosya Hafızası',
            onPressed: () => context.pushNamed(
              AppRoutes.caseMemory,
              pathParameters: <String, String>{'caseId': caseId},
            ),
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: <Widget>[
            Expanded(child: _buildBody(context, chat, controller)),
            EmsalistComposer(
              onSend: chat.conversationId == null
                  ? null
                  : (String text) => controller.sendMessage(text),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildBody(
    BuildContext context,
    ChatState chat,
    ChatController controller,
  ) {
    if (chat.loading) {
      return const LoadingWidget(message: 'Sohbet yükleniyor');
    }
    if (chat.error != null && chat.messages.isEmpty) {
      return AppErrorWidget(
        message: _messageFor(chat.error!),
        onRetry: controller.retryInitialLoad,
      );
    }
    if (chat.messages.isEmpty) {
      return const EmptyWidget(
        title: 'Sohbet boş',
        message: 'İlk mesajınızı yazarak başlayın.',
        icon: Icons.chat_bubble_outline,
      );
    }

    // reverse:true keeps the newest message pinned to the bottom and the
    // keyboard-friendly scroll anchored correctly on small screens.
    final int count = chat.messages.length + (chat.hasMore ? 1 : 0);
    return ListView.builder(
      reverse: true,
      padding: const EdgeInsets.symmetric(vertical: AppConstants.spacingSm),
      itemCount: count,
      itemBuilder: (BuildContext context, int index) {
        final int messageIndex = chat.messages.length - 1 - index;
        if (messageIndex < 0) {
          // Bottom-most (oldest) slot: "load more" affordance.
          return _LoadMoreButton(
            loading: chat.loadingMore,
            onPressed: controller.loadMore,
          );
        }
        final ChatMessage message = chat.messages[messageIndex];
        return _ChatBubble(
          message: message,
          onRetry: () => controller.retryMessage(message.clientRequestId),
        );
      },
    );
  }

  static String _messageFor(Object error) {
    if (error is ApiException) {
      return error.message;
    }
    return 'Sohbet yüklenemedi.';
  }
}

class _LoadMoreButton extends StatelessWidget {
  const _LoadMoreButton({required this.loading, required this.onPressed});

  final bool loading;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(AppConstants.spacingMd),
      child: Center(
        child: loading
            ? const SizedBox(
                height: 20,
                width: 20,
                child: CircularProgressIndicator(strokeWidth: 2),
              )
            : TextButton(
                onPressed: onPressed,
                child: const Text('Daha eski mesajları yükle'),
              ),
      ),
    );
  }
}

class _ChatBubble extends StatelessWidget {
  const _ChatBubble({required this.message, required this.onRetry});

  final ChatMessage message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final bool isUser = message.isUser;
    final Color bubbleColor = isUser
        ? theme.colorScheme.primary
        : theme.colorScheme.surfaceContainerHighest;
    final Color textColor = isUser
        ? theme.colorScheme.onPrimary
        : theme.colorScheme.onSurface;

    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxWidth: MediaQuery.sizeOf(context).width * 0.85,
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(
            horizontal: AppConstants.spacingMd,
            vertical: AppConstants.spacingXs,
          ),
          child: Column(
            crossAxisAlignment: isUser
                ? CrossAxisAlignment.end
                : CrossAxisAlignment.start,
            children: <Widget>[
              Container(
                padding: const EdgeInsets.all(AppConstants.spacingMd),
                decoration: BoxDecoration(
                  color: bubbleColor,
                  borderRadius: BorderRadius.circular(AppConstants.radiusMd),
                ),
                child: Text(
                  message.content,
                  style: theme.textTheme.bodyMedium?.copyWith(color: textColor),
                ),
              ),
              if (isUser) _StatusLine(message: message, onRetry: onRetry),
            ],
          ),
        ),
      ),
    );
  }
}

class _StatusLine extends StatelessWidget {
  const _StatusLine({required this.message, required this.onRetry});

  final ChatMessage message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    switch (message.status) {
      case ChatMessageStatus.sending:
        return Padding(
          padding: const EdgeInsets.only(top: AppConstants.spacingXs),
          child: Text(
            'Gönderiliyor…',
            style: theme.textTheme.labelSmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        );
      case ChatMessageStatus.sent:
        return Padding(
          padding: const EdgeInsets.only(top: AppConstants.spacingXs),
          child: Text(
            'Gönderildi',
            style: theme.textTheme.labelSmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        );
      case ChatMessageStatus.failed:
        return Padding(
          padding: const EdgeInsets.only(top: AppConstants.spacingXs),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Icon(
                Icons.error_outline,
                size: 14,
                color: theme.colorScheme.error,
              ),
              const SizedBox(width: AppConstants.spacingXs),
              Text(
                'Gönderilemedi',
                style: theme.textTheme.labelSmall?.copyWith(
                  color: theme.colorScheme.error,
                ),
              ),
              TextButton(
                onPressed: onRetry,
                style: TextButton.styleFrom(
                  padding: const EdgeInsets.symmetric(
                    horizontal: AppConstants.spacingSm,
                  ),
                  minimumSize: const Size(0, 32),
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                ),
                child: const Text('Yeniden dene'),
              ),
            ],
          ),
        );
    }
  }
}
