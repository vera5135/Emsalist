import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/constants/app_constants.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/network/download_service.dart';
import '../application/draft_providers.dart';
import '../domain/draft_item.dart';

class DraftExportBar extends ConsumerWidget {
  const DraftExportBar({required this.caseId, required this.draftId, super.key});

  final String caseId;
  final String draftId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final DownloadService downloadService = ref.watch(
      downloadServiceProvider,
    );

    return Padding(
      padding: const EdgeInsets.symmetric(
        horizontal: AppConstants.spacingMd,
        vertical: AppConstants.spacingSm,
      ),
      child: Row(
        children: <Widget>[
          Expanded(
            child: _ExportButton(
              label: 'DOCX İndir',
              icon: Icons.description_outlined,
              onDownload: (BuildContext ctx) async {
                await _download(
                  ctx,
                  downloadService,
                  ref,
                  caseId,
                  draftId,
                  'docx',
                );
              },
            ),
          ),
          const SizedBox(width: AppConstants.spacingSm),
          Expanded(
            child: _ExportButton(
              label: 'PDF İndir',
              icon: Icons.picture_as_pdf_outlined,
              onDownload: (BuildContext ctx) async {
                await _download(
                  ctx,
                  downloadService,
                  ref,
                  caseId,
                  draftId,
                  'pdf',
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _download(
    BuildContext context,
    DownloadService downloadService,
    WidgetRef ref,
    String caseId,
    String draftId,
    String format,
  ) async {
    try {
      final DraftApi api = ref.read(draftApiProvider);

      final DownloadedFile file;
      if (format == 'docx') {
        file = await api.downloadDocx(caseId, draftId);
      } else {
        file = await api.downloadPdf(caseId, draftId);
      }

      await downloadService.saveAndOpen(file);
    } on ApiException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(safeErrorMessage(e.code ?? ''))),
        );
      }
    } on Object {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Dışa aktarma başarısız oldu.')),
        );
      }
    }
  }
}

class _ExportButton extends StatefulWidget {
  const _ExportButton({
    required this.label,
    required this.icon,
    required this.onDownload,
  });

  final String label;
  final IconData icon;
  final Future<void> Function(BuildContext ctx) onDownload;

  @override
  State<_ExportButton> createState() => _ExportButtonState();
}

class _ExportButtonState extends State<_ExportButton> {
  bool _loading = false;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: widget.label,
      child: FilledButton.tonal(
        onPressed: _loading
            ? null
            : () async {
                setState(() => _loading = true);
                try {
                  await widget.onDownload(context);
                } finally {
                  if (mounted) {
                    setState(() => _loading = false);
                  }
                }
              },
        child: _loading
            ? const SizedBox.square(
                dimension: 20,
                child: CircularProgressIndicator(strokeWidth: 2),
              )
            : Row(
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  Icon(widget.icon, size: 18),
                  const SizedBox(width: AppConstants.spacingXs),
                  Text(widget.label),
                ],
              ),
      ),
    );
  }
}
