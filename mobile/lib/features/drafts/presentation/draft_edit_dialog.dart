import 'package:flutter/material.dart';

import '../../../core/constants/app_constants.dart';
import '../domain/draft_item.dart';

Future<void> showEditParagraphDialog(
  BuildContext context, {
  required DraftParagraphItem paragraph,
  required Future<void> Function(String text) onSave,
}) async {
  final TextEditingController controller = TextEditingController(
    text: paragraph.text,
  );
  final GlobalKey<FormState> formKey = GlobalKey<FormState>();
  bool saving = false;

  await showDialog<void>(
    context: context,
    barrierDismissible: false,
    builder: (BuildContext dialogContext) {
      return StatefulBuilder(
        builder: (BuildContext ctx, StateSetter setDialogState) {
          return AlertDialog(
            title: Text('Paragrafı Düzenle — ${paragraph.label}'),
            content: SingleChildScrollView(
              child: Form(
                key: formKey,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      'Sürüm: ${paragraph.version}',
                      style: Theme.of(ctx).textTheme.bodySmall,
                    ),
                    const SizedBox(height: AppConstants.spacingMd),
                    SizedBox(
                      width: MediaQuery.of(ctx).size.width * 0.8,
                      child: TextFormField(
                        controller: controller,
                        maxLength: 50000,
                        minLines: 6,
                        maxLines: 20,
                        decoration: const InputDecoration(
                          labelText: 'Paragraf metni',
                          border: OutlineInputBorder(),
                          alignLabelWithHint: true,
                        ),
                        validator: (String? value) {
                          if (value == null || value.trim().isEmpty) {
                            return 'Paragraf metni boş olamaz';
                          }
                          if (value.length > 50000) {
                            return 'En fazla 50.000 karakter';
                          }
                          return null;
                        },
                      ),
                    ),
                  ],
                ),
              ),
            ),
            actions: <Widget>[
              TextButton(
                onPressed: saving
                    ? null
                    : () => Navigator.of(dialogContext).pop(),
                child: const Text('İptal'),
              ),
              Semantics(
                button: true,
                label: 'Kaydet',
                child: FilledButton(
                  onPressed: saving
                      ? null
                      : () async {
                          if (!formKey.currentState!.validate()) return;
                          setDialogState(() => saving = true);
                          try {
                            await onSave(controller.text.trim());
                            if (dialogContext.mounted) {
                              Navigator.of(dialogContext).pop();
                            }
                          } on Object {
                            setDialogState(() => saving = false);
                            if (dialogContext.mounted) {
                              ScaffoldMessenger.of(dialogContext).showSnackBar(
                                const SnackBar(
                                  content: Text('Paragraf düzenlenemedi.'),
                                ),
                              );
                            }
                          }
                        },
                  child: saving
                      ? const SizedBox.square(
                          dimension: 20,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Text('Kaydet'),
                ),
              ),
            ],
          );
        },
      );
    },
  );
}
