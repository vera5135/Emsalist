import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/constants/app_constants.dart';
import '../../core/providers/theme_provider.dart';

class AppearanceScreen extends ConsumerWidget {
  const AppearanceScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final ThemeData theme = Theme.of(context);
    final ThemeMode current = ref.watch(themeModeProvider);
    final ThemeModeNotifier notifier = ref.read(themeModeProvider.notifier);

    return Semantics(
      container: true,
      label: 'Görünüm ayarları',
      child: Padding(
        padding: const EdgeInsets.symmetric(
          vertical: AppConstants.spacingMd,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Padding(
              padding: const EdgeInsets.symmetric(
                horizontal: AppConstants.spacingLg,
              ),
              child: Text('Görünüm', style: theme.textTheme.titleLarge),
            ),
            const SizedBox(height: AppConstants.spacingSm),
            _ThemeOption(
              label: 'Otomatik',
              icon: Icons.brightness_auto_outlined,
              value: ThemeMode.system,
              groupValue: current,
              onChanged: notifier.setThemeMode,
            ),
            _ThemeOption(
              label: 'Açık',
              icon: Icons.light_mode_outlined,
              value: ThemeMode.light,
              groupValue: current,
              onChanged: notifier.setThemeMode,
            ),
            _ThemeOption(
              label: 'Koyu',
              icon: Icons.dark_mode_outlined,
              value: ThemeMode.dark,
              groupValue: current,
              onChanged: notifier.setThemeMode,
            ),
          ],
        ),
      ),
    );
  }
}

class _ThemeOption extends StatelessWidget {
  const _ThemeOption({
    required this.label,
    required this.icon,
    required this.value,
    required this.groupValue,
    required this.onChanged,
  });

  final String label;
  final IconData icon;
  final ThemeMode value;
  final ThemeMode groupValue;
  final ValueChanged<ThemeMode> onChanged;

  @override
  Widget build(BuildContext context) {
    final bool selected = value == groupValue;
    return Semantics(
      selected: selected,
      inMutuallyExclusiveGroup: true,
      label: label,
      child: RadioListTile<ThemeMode>(
        value: value,
        groupValue: groupValue,
        onChanged: (ThemeMode? mode) {
          if (mode != null) {
            onChanged(mode);
          }
        },
        title: Text(label),
        secondary: Icon(icon),
        controlAffinity: ListTileControlAffinity.trailing,
      ),
    );
  }
}
