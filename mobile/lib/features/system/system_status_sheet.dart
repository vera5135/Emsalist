import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/config/api_configuration_exception.dart';
import '../../core/constants/app_constants.dart';
import '../../core/data/system/system_repository.dart';
import '../../core/network/api_exception.dart';
import '../../core/providers/system_status_provider.dart';

/// Bottom sheet showing backend connectivity, version, environment and health.
///
/// Opened from the app bar overflow menu. There is no persistent home-screen
/// badge.
class SystemStatusSheet extends ConsumerWidget {
  const SystemStatusSheet({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final AsyncValue<SystemStatus> status = ref.watch(systemStatusProvider);
    final String environment = ref.watch(appEnvironmentProvider).label;

    return SafeArea(
      top: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(
          AppConstants.spacingLg,
          AppConstants.spacingSm,
          AppConstants.spacingLg,
          AppConstants.spacingLg,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Semantics(
              header: true,
              child: Text(
                'Sistem Durumu',
                style: Theme.of(context).textTheme.titleLarge,
              ),
            ),
            const SizedBox(height: AppConstants.spacingMd),
            _EnvironmentRow(environment: environment),
            const SizedBox(height: AppConstants.spacingMd),
            status.when(
              loading: () => const _StatusLoading(),
              error: (Object error, _) => _StatusError(
                error: error,
                onRetry: () => ref.invalidate(systemStatusProvider),
              ),
              data: (SystemStatus data) => _StatusData(status: data),
            ),
          ],
        ),
      ),
    );
  }
}

class _EnvironmentRow extends StatelessWidget {
  const _EnvironmentRow({required this.environment});

  final String environment;

  @override
  Widget build(BuildContext context) {
    return _InfoRow(label: 'Ortam', value: environment);
  }
}

class _StatusLoading extends StatelessWidget {
  const _StatusLoading();

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: 'Sistem durumu yükleniyor',
      child: const Padding(
        padding: EdgeInsets.symmetric(vertical: AppConstants.spacingLg),
        child: Center(child: CircularProgressIndicator()),
      ),
    );
  }
}

class _StatusData extends StatelessWidget {
  const _StatusData({required this.status});

  final SystemStatus status;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        _HealthRow(health: status.health),
        const SizedBox(height: AppConstants.spacingSm),
        const _InfoRow(label: 'Bağlantı', value: 'Bağlı'),
        const SizedBox(height: AppConstants.spacingSm),
        _InfoRow(label: 'Sürüm', value: status.version ?? 'Bilinmiyor'),
        const SizedBox(height: AppConstants.spacingSm),
        _InfoRow(label: 'API', value: status.apiVersion ?? 'Bilinmiyor'),
        if (status.hasCommit) ...<Widget>[
          const SizedBox(height: AppConstants.spacingSm),
          _InfoRow(label: 'Commit', value: status.commit!),
        ],
        if ((status.serviceName ?? '').isNotEmpty) ...<Widget>[
          const SizedBox(height: AppConstants.spacingSm),
          _InfoRow(label: 'Servis', value: status.serviceName!),
        ],
        const SizedBox(height: AppConstants.spacingMd),
        Text(
          'Backend ortamı: ${status.environment ?? 'Bilinmiyor'}',
          style: theme.textTheme.bodySmall?.copyWith(
            color: theme.colorScheme.onSurfaceVariant,
          ),
        ),
      ],
    );
  }
}

class _HealthRow extends StatelessWidget {
  const _HealthRow({required this.health});

  final BackendHealth health;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final (IconData icon, Color color, String label) = switch (health) {
      BackendHealth.healthy => (
        Icons.check_circle_outline,
        const Color(0xFF2E7D32),
        'Sağlıklı',
      ),
      BackendHealth.degraded => (
        Icons.error_outline,
        const Color(0xFFF9A825),
        'Kısmi',
      ),
      BackendHealth.unhealthy => (
        Icons.cancel_outlined,
        const Color(0xFFC62828),
        'Sağlıksız',
      ),
      BackendHealth.unknown => (
        Icons.help_outline,
        theme.colorScheme.onSurfaceVariant,
        'Bilinmiyor',
      ),
    };

    return Semantics(
      label: 'Sağlık durumu: $label',
      child: Row(
        children: <Widget>[
          Icon(icon, color: color),
          const SizedBox(width: AppConstants.spacingSm),
          Text('Sağlık', style: theme.textTheme.bodyMedium),
          const SizedBox(width: AppConstants.spacingMd),
          Expanded(
            child: Text(
              label,
              textAlign: TextAlign.end,
              overflow: TextOverflow.ellipsis,
              style: theme.textTheme.bodyMedium?.copyWith(
                color: color,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _StatusError extends StatelessWidget {
  const _StatusError({required this.error, required this.onRetry});

  final Object error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final (String title, String message, String? correlationId) = _describe(
      error,
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Row(
          children: <Widget>[
            Icon(Icons.cloud_off_outlined, color: theme.colorScheme.error),
            const SizedBox(width: AppConstants.spacingSm),
            Expanded(
              child: Text(
                title,
                style: theme.textTheme.titleMedium?.copyWith(
                  color: theme.colorScheme.error,
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: AppConstants.spacingSm),
        Text(message, style: theme.textTheme.bodyMedium),
        if (correlationId != null) ...<Widget>[
          const SizedBox(height: AppConstants.spacingSm),
          SelectableText(
            'Hata kimliği: $correlationId',
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        ],
        const SizedBox(height: AppConstants.spacingMd),
        Semantics(
          button: true,
          label: 'Yeniden dene',
          child: FilledButton.icon(
            onPressed: onRetry,
            icon: const Icon(Icons.refresh),
            label: const Text('Yeniden Dene'),
          ),
        ),
      ],
    );
  }

  static (String, String, String?) _describe(Object error) {
    if (error is ApiConfigurationException) {
      return (
        'Yapılandırma eksik',
        'Bu ortam için API adresi tanımlı değil. Uygulama ağ isteği yapmadı.',
        null,
      );
    }
    if (error is ApiException) {
      final String title = error.kind == ApiErrorKind.network
          ? 'Çevrimdışı'
          : 'Bağlantı hatası';
      return (title, error.message, error.correlationId);
    }
    return ('Bağlantı hatası', 'Beklenmeyen bir hata oluştu.', null);
  }
}

class _InfoRow extends StatelessWidget {
  const _InfoRow({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Row(
      children: <Widget>[
        Text(label, style: theme.textTheme.bodyMedium),
        const SizedBox(width: AppConstants.spacingMd),
        Expanded(
          child: Text(
            value,
            textAlign: TextAlign.end,
            overflow: TextOverflow.ellipsis,
            style: theme.textTheme.bodyMedium?.copyWith(
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
      ],
    );
  }
}
