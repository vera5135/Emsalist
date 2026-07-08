import 'models/health_status_dto.dart';
import 'models/server_version_dto.dart';
import 'system_api.dart';

/// Overall backend health as a domain enum, independent of transport DTOs.
enum BackendHealth {
  healthy,
  degraded,
  unhealthy,
  unknown;

  static BackendHealth fromRaw(String? raw) {
    switch (raw?.trim().toLowerCase()) {
      case 'healthy':
        return BackendHealth.healthy;
      case 'degraded':
        return BackendHealth.degraded;
      case 'unhealthy':
        return BackendHealth.unhealthy;
      default:
        return BackendHealth.unknown;
    }
  }
}

/// Domain snapshot of backend system status shown in the System Status UI.
class SystemStatus {
  const SystemStatus({
    required this.health,
    this.application,
    this.version,
    this.apiVersion,
    this.commit,
    this.environment,
    this.serviceName,
  });

  final BackendHealth health;
  final String? application;
  final String? version;
  final String? apiVersion;
  final String? commit;
  final String? environment;
  final String? serviceName;

  bool get hasCommit => (commit ?? '').isNotEmpty && commit != 'unknown';
}

/// Coordinates the selected system endpoints and maps DTOs to the domain
/// [SystemStatus]. UI depends on this repository, never on Dio.
class SystemRepository {
  const SystemRepository(this._api);

  final SystemApi _api;

  Future<SystemStatus> fetchStatus({Object? cancelToken}) async {
    final ServerVersionDto version = await _api.fetchVersion(
      cancelToken: cancelToken,
    );
    final HealthStatusDto health = await _api.fetchHealth(
      cancelToken: cancelToken,
    );

    return SystemStatus(
      health: BackendHealth.fromRaw(health.status),
      application: version.application,
      version: version.version,
      apiVersion: version.apiVersion,
      commit: version.commit,
      environment: version.environment,
      serviceName: health.service,
    );
  }
}
