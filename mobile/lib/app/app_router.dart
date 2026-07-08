import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../features/assistant/assistant_screen.dart';

class AppRoutes {
  const AppRoutes._();

  static const String assistant = 'assistant';
  static const String cases = 'cases';
  static const String sources = 'sources';
  static const String drafts = 'drafts';

  static const String assistantPath = '/assistant';
  static const String casesPath = '/cases';
  static const String sourcesPath = '/sources';
  static const String draftsPath = '/drafts';
}

class _NavDestination {
  const _NavDestination({
    required this.path,
    required this.label,
    required this.icon,
    required this.selectedIcon,
  });

  final String path;
  final String label;
  final IconData icon;
  final IconData selectedIcon;
}

const List<_NavDestination> _destinations = <_NavDestination>[
  _NavDestination(
    path: AppRoutes.assistantPath,
    label: 'Asistan',
    icon: Icons.chat_bubble_outline,
    selectedIcon: Icons.chat_bubble,
  ),
  _NavDestination(
    path: AppRoutes.casesPath,
    label: 'Dosyalar',
    icon: Icons.folder_outlined,
    selectedIcon: Icons.folder,
  ),
  _NavDestination(
    path: AppRoutes.sourcesPath,
    label: 'Kaynaklar',
    icon: Icons.menu_book_outlined,
    selectedIcon: Icons.menu_book,
  ),
  _NavDestination(
    path: AppRoutes.draftsPath,
    label: 'Taslaklar',
    icon: Icons.edit_note_outlined,
    selectedIcon: Icons.edit_note,
  ),
];

GoRouter createAppRouter() {
  return GoRouter(
    initialLocation: AppRoutes.assistantPath,
    routes: <RouteBase>[
      ShellRoute(
        builder: (BuildContext context, GoRouterState state, Widget child) {
          return _ScaffoldWithNavBar(location: state.uri.path, child: child);
        },
        routes: <RouteBase>[
          GoRoute(
            path: AppRoutes.assistantPath,
            name: AppRoutes.assistant,
            builder: (BuildContext context, GoRouterState state) =>
                const AssistantScreen(),
          ),
          GoRoute(
            path: AppRoutes.casesPath,
            name: AppRoutes.cases,
            builder: (BuildContext context, GoRouterState state) =>
                const _PlaceholderScreen(
              title: 'Dosyalar',
              icon: Icons.folder_outlined,
            ),
          ),
          GoRoute(
            path: AppRoutes.sourcesPath,
            name: AppRoutes.sources,
            builder: (BuildContext context, GoRouterState state) =>
                const _PlaceholderScreen(
              title: 'Kaynaklar',
              icon: Icons.menu_book_outlined,
            ),
          ),
          GoRoute(
            path: AppRoutes.draftsPath,
            name: AppRoutes.drafts,
            builder: (BuildContext context, GoRouterState state) =>
                const _PlaceholderScreen(
              title: 'Taslaklar',
              icon: Icons.edit_note_outlined,
            ),
          ),
        ],
      ),
    ],
  );
}

class _ScaffoldWithNavBar extends StatelessWidget {
  const _ScaffoldWithNavBar({required this.location, required this.child});

  final String location;
  final Widget child;

  int get _currentIndex {
    final int index =
        _destinations.indexWhere((_NavDestination d) => location == d.path);
    return index < 0 ? 0 : index;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: child,
      bottomNavigationBar: NavigationBar(
        selectedIndex: _currentIndex,
        onDestinationSelected: (int index) =>
            context.go(_destinations[index].path),
        destinations: _destinations
            .map(
              (_NavDestination d) => NavigationDestination(
                icon: Icon(d.icon),
                selectedIcon: Icon(d.selectedIcon),
                label: d.label,
                tooltip: d.label,
              ),
            )
            .toList(),
      ),
    );
  }
}

class _PlaceholderScreen extends StatelessWidget {
  const _PlaceholderScreen({required this.title, required this.icon});

  final String title;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: Text(title)),
      body: Center(
        child: Semantics(
          label: '$title ekranı yakında',
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Icon(icon, size: 48, color: theme.colorScheme.outline),
              const SizedBox(height: 16),
              Text('$title yakında', style: theme.textTheme.titleMedium),
            ],
          ),
        ),
      ),
    );
  }
}
