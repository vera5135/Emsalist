import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/models/uyap_status.dart';
import '../../core/providers/uyap_provider.dart';

class UyapStatusIcon extends ConsumerWidget {
  const UyapStatusIcon({super.key, this.onTap});

  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final UyapState state = ref.watch(uyapProvider);
    final String semantics = state.hasNewMovements
        ? '${state.status.semanticsLabel}, ${state.movementCount} yeni hareket'
        : state.status.semanticsLabel;

    return Semantics(
      button: true,
      label: semantics,
      child: Tooltip(
        message: state.hasNewMovements
            ? '${state.status.label} • ${state.movementCount} yeni hareket'
            : state.status.label,
        child: IconButton(
          onPressed: onTap,
          icon: Stack(
            clipBehavior: Clip.none,
            children: <Widget>[
              Icon(state.status.icon, color: state.status.color),
              if (state.hasNewMovements)
                Positioned(
                  right: -4,
                  top: -4,
                  child: _MovementBadge(count: state.movementCount),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _MovementBadge extends StatelessWidget {
  const _MovementBadge({required this.count});

  final int count;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
      constraints: const BoxConstraints(minWidth: 16),
      decoration: BoxDecoration(
        color: theme.colorScheme.error,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(
        count > 9 ? '9+' : '$count',
        textAlign: TextAlign.center,
        style: theme.textTheme.labelSmall?.copyWith(
          color: theme.colorScheme.onError,
          fontWeight: FontWeight.bold,
          fontSize: 10,
        ),
      ),
    );
  }
}
