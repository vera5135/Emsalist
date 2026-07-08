import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/constants/app_constants.dart';
import '../../core/models/message_model.dart';
import '../../core/widgets/state_widgets.dart';
import '../../design_system/components/emsalist_app_bar.dart';
import '../../design_system/components/emsalist_composer.dart';
import '../cases/case_drawer.dart';
import '../cases/case_summary_sheet.dart';
import 'widgets/message_card.dart';

class AssistantScreen extends ConsumerStatefulWidget {
  const AssistantScreen({super.key});

  @override
  ConsumerState<AssistantScreen> createState() => _AssistantScreenState();
}

class _AssistantScreenState extends ConsumerState<AssistantScreen> {
  late List<MessageModel> _messages;

  @override
  void initState() {
    super.initState();
    _messages = MessageModel.mockConversation().reversed.toList();
  }

  void _handleSend(String text) {
    setState(() {
      _messages.insert(
        0,
        MessageModel(
          id: 'local-${DateTime.now().microsecondsSinceEpoch}',
          sender: MessageSender.user,
          timestamp: DateTime.now(),
          text: text,
        ),
      );
    });
  }

  void _openSummary() {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (BuildContext ctx) => const CaseSummarySheet(),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: EmsalistAppBar(onSummary: _openSummary),
      drawer: const CaseDrawer(),
      body: Column(
        children: <Widget>[
          Expanded(
            child: _messages.isEmpty
                ? const EmptyWidget(
                    title: 'Sohbet boş',
                    message: 'İlk mesajınızı yazarak başlayın.',
                    icon: Icons.chat_bubble_outline,
                  )
                : ListView.builder(
                    reverse: true,
                    padding: const EdgeInsets.symmetric(
                      vertical: AppConstants.spacingMd,
                    ),
                    itemCount: _messages.length,
                    itemBuilder: (BuildContext ctx, int index) {
                      return MessageCard(message: _messages[index]);
                    },
                  ),
          ),
          EmsalistComposer(onSend: _handleSend),
        ],
      ),
    );
  }
}
