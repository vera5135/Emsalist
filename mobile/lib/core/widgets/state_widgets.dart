import 'package:flutter/material.dart';

import '../constants/app_constants.dart';

class LoadingWidget extends StatelessWidget {
  const LoadingWidget({super.key, this.message});

  final String? message;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: message ?? 'Yükleniyor',
      liveRegion: true,
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            const CircularProgressIndicator(),
            if (message != null) ...<Widget>[
              const SizedBox(height: AppConstants.spacingMd),
              Text(message!, textAlign: TextAlign.center),
            ],
          ],
        ),
      ),
    );
  }
}

class EmptyWidget extends StatelessWidget {
  const EmptyWidget({
    super.key,
    this.title = 'Henüz içerik yok',
    this.message,
    this.icon = Icons.inbox_outlined,
  });

  final String title;
  final String? message;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Semantics(
      label: 'Boş durum: $title',
      child: Center(
        child: Padding(
          padding: const EdgeInsets.all(AppConstants.spacingLg),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Icon(icon, size: 48, color: theme.colorScheme.outline),
              const SizedBox(height: AppConstants.spacingMd),
              Text(title, style: theme.textTheme.titleMedium),
              if (message != null) ...<Widget>[
                const SizedBox(height: AppConstants.spacingSm),
                Text(
                  message!,
                  textAlign: TextAlign.center,
                  style: theme.textTheme.bodyMedium,
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class OfflineWidget extends StatelessWidget {
  const OfflineWidget({super.key, this.onRetry});

  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Semantics(
      label: 'Çevrimdışı',
      child: Center(
        child: Padding(
          padding: const EdgeInsets.all(AppConstants.spacingLg),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Icon(Icons.wifi_off, size: 48, color: theme.colorScheme.outline),
              const SizedBox(height: AppConstants.spacingMd),
              Text('Çevrimdışısınız', style: theme.textTheme.titleMedium),
              const SizedBox(height: AppConstants.spacingSm),
              Text(
                'Bağlantı kurulduğunda tekrar deneyin.',
                textAlign: TextAlign.center,
                style: theme.textTheme.bodyMedium,
              ),
              if (onRetry != null) ...<Widget>[
                const SizedBox(height: AppConstants.spacingMd),
                FilledButton.tonal(
                  onPressed: onRetry,
                  child: const Text('Tekrar Dene'),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class AppErrorWidget extends StatelessWidget {
  const AppErrorWidget({
    super.key,
    this.title = 'Bir şeyler ters gitti',
    this.message,
    this.onRetry,
  });

  final String title;
  final String? message;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Semantics(
      label: 'Hata: $title',
      child: Center(
        child: Padding(
          padding: const EdgeInsets.all(AppConstants.spacingLg),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Icon(
                Icons.error_outline,
                size: 48,
                color: theme.colorScheme.error,
              ),
              const SizedBox(height: AppConstants.spacingMd),
              Text(title, style: theme.textTheme.titleMedium),
              if (message != null) ...<Widget>[
                const SizedBox(height: AppConstants.spacingSm),
                Text(
                  message!,
                  textAlign: TextAlign.center,
                  style: theme.textTheme.bodyMedium,
                ),
              ],
              if (onRetry != null) ...<Widget>[
                const SizedBox(height: AppConstants.spacingMd),
                Semantics(
                  button: true,
                  label: 'Tekrar dene',
                  child: FilledButton(
                    onPressed: onRetry,
                    child: const Text('Tekrar Dene'),
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
