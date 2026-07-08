import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers/case_provider.dart';
import '../../features/settings/appearance_screen.dart';
import '../../features/system/system_status_sheet.dart';
import '../../features/uyap/uyap_sheet.dart';
import '../../features/uyap/uyap_status_icon.dart';

enum AppBarMenuAction { summary, appearance, systemStatus, share }

class EmsalistAppBar extends ConsumerWidget implements PreferredSizeWidget {
  const EmsalistAppBar({super.key, this.title, this.subtitle, this.onSummary});

  final String? title;
  final String? subtitle;
  final VoidCallback? onSummary;

  @override
  Size get preferredSize => const Size.fromHeight(kToolbarHeight + 8);

  void _onMenuSelected(BuildContext context, AppBarMenuAction action) {
    switch (action) {
      case AppBarMenuAction.summary:
        onSummary?.call();
        break;
      case AppBarMenuAction.appearance:
        showModalBottomSheet<void>(
          context: context,
          showDragHandle: true,
          builder: (BuildContext ctx) => const AppearancePicker(),
        );
        break;
      case AppBarMenuAction.systemStatus:
        showModalBottomSheet<void>(
          context: context,
          isScrollControlled: true,
          showDragHandle: true,
          builder: (BuildContext ctx) => const SystemStatusSheet(),
        );
        break;
      case AppBarMenuAction.share:
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Paylaşım henüz uygulanmadı')),
        );
        break;
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final ThemeData theme = Theme.of(context);
    final CaseState caseState = ref.watch(caseProvider);
    final String resolvedTitle =
        title ?? caseState.activeCase?.title ?? 'Emsalist';
    final String resolvedSubtitle =
        subtitle ?? caseState.activeCase?.legalTopic ?? 'Asistan';

    return AppBar(
      leading: Builder(
        builder: (BuildContext ctx) => IconButton(
          icon: const Icon(Icons.menu),
          tooltip: 'Dosyalar',
          onPressed: () => Scaffold.of(ctx).openDrawer(),
        ),
      ),
      titleSpacing: 0,
      title: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.center,
        children: <Widget>[
          Text(
            resolvedTitle,
            style: theme.textTheme.titleMedium,
            overflow: TextOverflow.ellipsis,
          ),
          Text(
            resolvedSubtitle,
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ),
      actions: <Widget>[
        UyapStatusIcon(
          onTap: () => showModalBottomSheet<void>(
            context: context,
            showDragHandle: true,
            builder: (BuildContext ctx) => const UyapSheet(),
          ),
        ),
        PopupMenuButton<AppBarMenuAction>(
          icon: const Icon(Icons.more_vert),
          tooltip: 'Diğer seçenekler',
          onSelected: (AppBarMenuAction action) =>
              _onMenuSelected(context, action),
          itemBuilder: (BuildContext ctx) => <PopupMenuEntry<AppBarMenuAction>>[
            const PopupMenuItem<AppBarMenuAction>(
              value: AppBarMenuAction.summary,
              child: ListTile(
                leading: Icon(Icons.summarize_outlined),
                title: Text('Dosya Özeti'),
                contentPadding: EdgeInsets.zero,
              ),
            ),
            const PopupMenuItem<AppBarMenuAction>(
              value: AppBarMenuAction.appearance,
              child: ListTile(
                leading: Icon(Icons.brightness_6_outlined),
                title: Text('Görünüm'),
                contentPadding: EdgeInsets.zero,
              ),
            ),
            const PopupMenuItem<AppBarMenuAction>(
              value: AppBarMenuAction.systemStatus,
              child: ListTile(
                leading: Icon(Icons.monitor_heart_outlined),
                title: Text('Sistem Durumu'),
                contentPadding: EdgeInsets.zero,
              ),
            ),
            const PopupMenuItem<AppBarMenuAction>(
              value: AppBarMenuAction.share,
              child: ListTile(
                leading: Icon(Icons.ios_share),
                title: Text('Paylaş'),
                contentPadding: EdgeInsets.zero,
              ),
            ),
          ],
        ),
      ],
    );
  }
}
