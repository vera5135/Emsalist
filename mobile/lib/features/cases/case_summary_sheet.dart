import 'package:flutter/material.dart';

import '../../core/constants/app_constants.dart';

class CaseSummarySheet extends StatelessWidget {
  const CaseSummarySheet({super.key});

  static const Map<String, List<String>> _sections = <String, List<String>>{
    'Taraflar': <String>['Davacı: Ahmet Yılmaz', 'Davalı: XYZ Otomotiv A.Ş.'],
    'Kronoloji': <String>[
      '12.01.2024 — Araç satın alındı',
      '03.03.2024 — Ayıp fark edildi',
      '10.03.2024 — Satıcıya ihbar edildi',
    ],
    'Talepler': <String>['Bedel iadesi', 'Ayıp oranında indirim (alternatif)'],
    'Belgeler': <String>['Satış Sözleşmesi.pdf', 'Servis Raporu.pdf'],
    'Eksikler': <String>['Ayıp ihbar tarihinin belgesi'],
    'Çelişkiler': <String>['İhbar tarihi ifadeleri arasında tutarsızlık'],
    'Riskler': <String>['Zamanaşımı riski (yüksek)'],
    'Süreler': <String>['Dava açma süresi: 2 yıl'],
  };

  static const Map<String, IconData> _icons = <String, IconData>{
    'Taraflar': Icons.people_outline,
    'Kronoloji': Icons.timeline_outlined,
    'Talepler': Icons.request_page_outlined,
    'Belgeler': Icons.folder_outlined,
    'Eksikler': Icons.help_outline,
    'Çelişkiler': Icons.compare_arrows_outlined,
    'Riskler': Icons.warning_amber_outlined,
    'Süreler': Icons.schedule_outlined,
  };

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return DraggableScrollableSheet(
      expand: false,
      initialChildSize: 0.7,
      minChildSize: 0.4,
      maxChildSize: 0.95,
      builder: (BuildContext ctx, ScrollController controller) {
        return Semantics(
          container: true,
          label: 'Dosya özeti',
          child: ListView(
            controller: controller,
            padding: const EdgeInsets.all(AppConstants.spacingMd),
            children: <Widget>[
              Text('Dosya Özeti', style: theme.textTheme.titleLarge),
              const SizedBox(height: AppConstants.spacingMd),
              ..._sections.entries.map((MapEntry<String, List<String>> entry) {
                return Padding(
                  padding: const EdgeInsets.only(
                    bottom: AppConstants.spacingMd,
                  ),
                  child: _SummarySection(
                    title: entry.key,
                    icon: _icons[entry.key] ?? Icons.notes_outlined,
                    items: entry.value,
                  ),
                );
              }),
            ],
          ),
        );
      },
    );
  }
}

class _SummarySection extends StatelessWidget {
  const _SummarySection({
    required this.title,
    required this.icon,
    required this.items,
  });

  final String title;
  final IconData icon;
  final List<String> items;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Semantics(
      container: true,
      label: '$title bölümü',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Icon(icon, size: 20, color: theme.colorScheme.primary),
              const SizedBox(width: AppConstants.spacingSm),
              Text(
                title,
                style: theme.textTheme.titleSmall?.copyWith(
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
          const SizedBox(height: AppConstants.spacingXs),
          ...items.map(
            (String item) => Padding(
              padding: const EdgeInsets.only(
                left: AppConstants.spacingLg,
                top: AppConstants.spacingXs,
              ),
              child: Text('• $item', style: theme.textTheme.bodyMedium),
            ),
          ),
        ],
      ),
    );
  }
}
