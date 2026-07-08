import 'package:flutter/material.dart';

import '../../core/constants/app_constants.dart';

class EmsalistComposer extends StatefulWidget {
  const EmsalistComposer({super.key, this.onSend});

  final ValueChanged<String>? onSend;

  @override
  State<EmsalistComposer> createState() => _EmsalistComposerState();
}

enum _ComposerAction { document, photo, uyap, voice }

class _EmsalistComposerState extends State<EmsalistComposer> {
  final TextEditingController _controller = TextEditingController();
  final FocusNode _focusNode = FocusNode();
  bool _hasText = false;

  @override
  void initState() {
    super.initState();
    _controller.addListener(_onChanged);
  }

  void _onChanged() {
    final bool hasText = _controller.text.trim().isNotEmpty;
    if (hasText != _hasText) {
      setState(() => _hasText = hasText);
    }
  }

  @override
  void dispose() {
    _controller.removeListener(_onChanged);
    _controller.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  void _send() {
    final String text = _controller.text.trim();
    if (text.isEmpty) {
      return;
    }
    widget.onSend?.call(text);
    _controller.clear();
  }

  void _onAddSelected(_ComposerAction action) {
    late final String label;
    switch (action) {
      case _ComposerAction.document:
        label = 'Belge ekleme';
        break;
      case _ComposerAction.photo:
        label = 'Fotoğraf ekleme';
        break;
      case _ComposerAction.uyap:
        label = 'UYAP’tan içe aktarma';
        break;
      case _ComposerAction.voice:
        label = 'Sesli giriş';
        break;
    }
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('$label henüz uygulanmadı')),
    );
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return SafeArea(
      top: false,
      child: Container(
        padding: const EdgeInsets.symmetric(
          horizontal: AppConstants.spacingSm,
          vertical: AppConstants.spacingSm,
        ),
        decoration: BoxDecoration(
          color: theme.colorScheme.surface,
          border: Border(
            top: BorderSide(color: theme.colorScheme.outlineVariant),
          ),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: <Widget>[
            PopupMenuButton<_ComposerAction>(
              icon: const Icon(Icons.add_circle_outline),
              tooltip: 'Ekle',
              onSelected: _onAddSelected,
              itemBuilder: (BuildContext ctx) =>
                  <PopupMenuEntry<_ComposerAction>>[
                const PopupMenuItem<_ComposerAction>(
                  value: _ComposerAction.document,
                  child: ListTile(
                    leading: Icon(Icons.description_outlined),
                    title: Text('Belge Ekle'),
                    contentPadding: EdgeInsets.zero,
                  ),
                ),
                const PopupMenuItem<_ComposerAction>(
                  value: _ComposerAction.photo,
                  child: ListTile(
                    leading: Icon(Icons.photo_outlined),
                    title: Text('Fotoğraf'),
                    contentPadding: EdgeInsets.zero,
                  ),
                ),
                const PopupMenuItem<_ComposerAction>(
                  value: _ComposerAction.uyap,
                  child: ListTile(
                    leading: Icon(Icons.gavel_outlined),
                    title: Text('UYAP’tan Al'),
                    contentPadding: EdgeInsets.zero,
                  ),
                ),
                const PopupMenuItem<_ComposerAction>(
                  value: _ComposerAction.voice,
                  child: ListTile(
                    leading: Icon(Icons.mic_none_outlined),
                    title: Text('Sesli Giriş'),
                    contentPadding: EdgeInsets.zero,
                  ),
                ),
              ],
            ),
            const SizedBox(width: AppConstants.spacingXs),
            Expanded(
              child: Semantics(
                textField: true,
                label: 'Mesaj yaz',
                child: TextField(
                  controller: _controller,
                  focusNode: _focusNode,
                  minLines: 1,
                  maxLines: 5,
                  keyboardType: TextInputType.multiline,
                  textInputAction: TextInputAction.newline,
                  decoration: InputDecoration(
                    hintText: 'Mesaj yazın…',
                    filled: true,
                    fillColor: theme.colorScheme.surfaceContainerHighest,
                    border: OutlineInputBorder(
                      borderRadius:
                          BorderRadius.circular(AppConstants.radiusLg),
                      borderSide: BorderSide.none,
                    ),
                    contentPadding: const EdgeInsets.symmetric(
                      horizontal: AppConstants.spacingMd,
                      vertical: AppConstants.spacingSm + 2,
                    ),
                  ),
                ),
              ),
            ),
            const SizedBox(width: AppConstants.spacingXs),
            Semantics(
              button: true,
              enabled: _hasText,
              label: 'Gönder',
              child: IconButton.filled(
                onPressed: _hasText ? _send : null,
                icon: const Icon(Icons.send),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
