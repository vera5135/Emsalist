import 'package:flutter/material.dart';

import '../../../core/constants/app_constants.dart';

/// Shown while the app restores any persisted session on startup
/// (auth status == unknown). Prevents a flash of the login screen before the
/// secure store has been read.
class AuthLoadingScreen extends StatelessWidget {
  const AuthLoadingScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Scaffold(
      body: Center(
        child: Semantics(
          label: 'Yükleniyor',
          liveRegion: true,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Text(AppConstants.appName, style: theme.textTheme.headlineSmall),
              const SizedBox(height: AppConstants.spacingLg),
              const CircularProgressIndicator(),
            ],
          ),
        ),
      ),
    );
  }
}
