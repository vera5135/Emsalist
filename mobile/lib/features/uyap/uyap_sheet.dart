import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../core/constants/app_constants.dart';
import '../../core/models/uyap_status.dart';
import '../../core/providers/uyap_provider.dart';

class UyapSheet extends ConsumerWidget {
  const UyapSheet({super.key});

  String _formatTimestamp(DateTime? timestamp) {
    if (timestamp == null) {
      return 'Bilinmiyor';
    }
    return DateFormat('dd.MM.yyyy HH:mm').format(timestamp);
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final ThemeData theme = Theme.of(context);
    final UyapState state = ref.watch(uyapProvider);
    final bool connecting = state.status == UyapStatus.connecting;

    return Semantics(
      container: true,
      label: 'UYAP durumu paneli',
      child: Padding(
        padding: const EdgeInsets.all(AppConstants.spacingLg),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Text('UYAP', style: theme.textTheme.titleLarge),
            const SizedBox(height: AppConstants.spacingMd),
            Row(
              children: <Widget>[
                Icon(state.status.icon, color: state.status.color),
                const SizedBox(width: AppConstants.spacingSm),
                Text(
                  state.status.label,
                  style: theme.textTheme.titleMedium
                      ?.copyWith(color: state.status.color),
                ),
              ],
            ),
            const SizedBox(height: AppConstants.spacingMd),
            _InfoRow(
              icon: Icons.schedule_outlined,
              label: 'Son kontrol',
              value: _formatTimestamp(state.lastChecked),
            ),
            const SizedBox(height: AppConstants.spacingSm),
            _InfoRow(
              icon: Icons.notifications_outlined,
              label: 'Yeni hareket',
              value: '${state.movementCount}',
            ),
            const SizedBox(height: AppConstants.spacingLg),
            Semantics(
              button: true,
              label: 'Yeniden bağlan',
              child: FilledButton.icon(
                onPressed: connecting
                    ? null
                    : () => ref.read(uyapProvider.notifier).reconnect(),
                icon: connecting
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.refresh),
                label: Text(connecting ? 'Bağlanıyor…' : 'Yeniden Bağlan'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _InfoRow extends StatelessWidget {
  const _InfoRow({
    required this.icon,
    required this.label,
    required this.value,
  });

  final IconData icon;
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Row(
      children: <Widget>[
        Icon(icon, size: 20, color: theme.colorScheme.onSurfaceVariant),
        const SizedBox(width: AppConstants.spacingSm),
        Text(label, style: theme.textTheme.bodyMedium),
        const Spacer(),
        Text(
          value,
          style: theme.textTheme.bodyMedium
              ?.copyWith(fontWeight: FontWeight.w600),
        ),
      ],
    );
  }
}
