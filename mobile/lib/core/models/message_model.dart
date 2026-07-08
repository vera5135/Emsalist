import 'package:flutter/material.dart';

enum MessageSender { user, assistant }

enum MessageType { text, card }

enum CardSubtype { missingInfo, source, risk, document }

@immutable
class MessageModel {
  const MessageModel({
    required this.id,
    required this.sender,
    required this.timestamp,
    this.text = '',
    this.type = MessageType.text,
    this.cardSubtype,
    this.cardData = const <String, Object?>{},
  });

  final String id;
  final MessageSender sender;
  final DateTime timestamp;
  final String text;
  final MessageType type;
  final CardSubtype? cardSubtype;
  final Map<String, Object?> cardData;

  bool get isUser => sender == MessageSender.user;

  static List<MessageModel> mockConversation() {
    final DateTime now = DateTime.now();
    return <MessageModel>[
      MessageModel(
        id: 'm1',
        sender: MessageSender.user,
        timestamp: now.subtract(const Duration(minutes: 10)),
        text:
            'Müvekkilim aldığı araçta ayıp olduğunu fark etti, ne yapmalıyız?',
      ),
      MessageModel(
        id: 'm2',
        sender: MessageSender.assistant,
        timestamp: now.subtract(const Duration(minutes: 9)),
        text:
            'Ayıplı mal iddianızı değerlendirebilmem için birkaç bilgiye ihtiyacım var.',
      ),
      MessageModel(
        id: 'm3',
        sender: MessageSender.assistant,
        timestamp: now.subtract(const Duration(minutes: 9)),
        type: MessageType.card,
        cardSubtype: CardSubtype.missingInfo,
        cardData: <String, Object?>{
          'description':
              'Aracın satın alma tarihi ve ayıbın fark edilme tarihi eksik.',
        },
      ),
      MessageModel(
        id: 'm4',
        sender: MessageSender.assistant,
        timestamp: now.subtract(const Duration(minutes: 8)),
        type: MessageType.card,
        cardSubtype: CardSubtype.source,
        cardData: <String, Object?>{
          'title': 'TBK m. 219 - Ayıptan Sorumluluk',
          'sourceType': 'Kanun',
          'verified': true,
          'relevance': 0.92,
        },
      ),
      MessageModel(
        id: 'm5',
        sender: MessageSender.assistant,
        timestamp: now.subtract(const Duration(minutes: 7)),
        type: MessageType.card,
        cardSubtype: CardSubtype.risk,
        cardData: <String, Object?>{
          'severity': 'high',
          'title': 'Zamanaşımı Riski',
          'description':
              'Ayıp ihbarı süresinin kaçırılması hak kaybına yol açabilir.',
        },
      ),
      MessageModel(
        id: 'm6',
        sender: MessageSender.assistant,
        timestamp: now.subtract(const Duration(minutes: 6)),
        type: MessageType.card,
        cardSubtype: CardSubtype.document,
        cardData: <String, Object?>{
          'name': 'Satış Sözleşmesi.pdf',
          'size': '1.2 MB',
          'status': 'uploaded',
          'progress': 1.0,
        },
      ),
    ];
  }
}
