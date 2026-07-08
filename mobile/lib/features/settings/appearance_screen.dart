import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers/theme_provider.dart';

class AppearancePicker extends StatelessWidget {
  const AppearancePicker({super.key});

  static const List<_ThemeEntry> _entries = <_ThemeEntry>[
    _ThemeEntry(
      label: 'Otomatik',
      icon: Icons.brightness_auto,
      mode: ThemeMode.system,
    ),
    _ThemeEntry(label: 'Açık', icon: Icons.light_mode, mode: ThemeMode.light),
    _ThemeEntry(label: 'Koyu', icon: Icons.dark_mode, mode: ThemeMode.dark),
  ];

  @override
  Widget build(BuildContext context) {
    return Consumer(
      builder: (BuildContext context, WidgetRef ref, Widget? child) {
        final ThemeMode currentMode = ref.watch(themeModeProvider);
        return Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Padding(
              padding: const EdgeInsets.all(16),
              child: Text(
                'Görünüm',
                style: Theme.of(context).textTheme.titleMedium,
              ),
            ),
            RadioGroup<ThemeMode>(
              groupValue: currentMode,
              onChanged: (ThemeMode? mode) {
                if (mode != null) {
                  ref.read(themeModeProvider.notifier).setThemeMode(mode);
                }
              },
              child: Column(
                children: <Widget>[
                  for (final _ThemeEntry entry in _entries)
                    Semantics(
                      selected: entry.mode == currentMode,
                      inMutuallyExclusiveGroup: true,
                      label: entry.label,
                      child: RadioListTile<ThemeMode>(
                        value: entry.mode,
                        title: Text(entry.label),
                        secondary: Icon(entry.icon),
                      ),
                    ),
                ],
              ),
            ),
          ],
        );
      },
    );
  }
}

class _ThemeEntry {
  const _ThemeEntry({
    required this.label,
    required this.icon,
    required this.mode,
  });

  final String label;
  final IconData icon;
  final ThemeMode mode;
}
