import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/constants/app_constants.dart';
import '../core/providers/theme_provider.dart';
import '../features/auth/application/auth_providers.dart';
import '../features/auth/application/auth_router_refresh.dart';
import '../features/auth/application/auth_state.dart';
import 'app_router.dart';
import 'app_theme.dart';

class EmsalistApp extends ConsumerStatefulWidget {
  const EmsalistApp({super.key});

  @override
  ConsumerState<EmsalistApp> createState() => _EmsalistAppState();
}

class _EmsalistAppState extends ConsumerState<EmsalistApp> {
  late final GoRouter _router = createAppRouter(
    refreshListenable: ref.read(authRouterRefreshProvider),
    authStatus: () => ref.read(authControllerProvider).status,
  );

  @override
  void initState() {
    super.initState();
    // Restore any persisted session before the first frame settles; the router
    // shows the splash while status is unknown.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(authControllerProvider.notifier).bootstrap();
    });
  }

  @override
  Widget build(BuildContext context) {
    final ThemeMode themeMode = ref.watch(themeModeProvider);
    // Keep the auth state alive for the app lifetime.
    ref.watch(authControllerProvider.select((AuthState s) => s.status));

    return MaterialApp.router(
      title: AppConstants.appName,
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light,
      darkTheme: AppTheme.dark,
      themeMode: themeMode,
      routerConfig: _router,
    );
  }
}
