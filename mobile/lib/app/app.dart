import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/constants/app_constants.dart';
import '../core/providers/theme_provider.dart';
import 'app_router.dart';
import 'app_theme.dart';

class EmsalistApp extends ConsumerStatefulWidget {
  const EmsalistApp({super.key});

  @override
  ConsumerState<EmsalistApp> createState() => _EmsalistAppState();
}

class _EmsalistAppState extends ConsumerState<EmsalistApp> {
  late final GoRouter _router = createAppRouter();

  @override
  Widget build(BuildContext context) {
    final ThemeMode themeMode = ref.watch(themeModeProvider);

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
