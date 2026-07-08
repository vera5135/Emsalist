import '../../network/api_client.dart';
import 'models/health_status_dto.dart';
import 'models/server_version_dto.dart';

/// Thin data source for backend system endpoints.
///
/// Only the selected read-only endpoints are exposed; this is not a generated
/// full-API client.
class SystemApi {
  const SystemApi(this._client);

  final ApiClient _client;

  static const String versionPath = '/api/v1/meta/version';
  static const String healthPath = '/health';

  Future<ServerVersionDto> fetchVersion({Object? cancelToken}) async {
    final Map<String, dynamic> json = await _client
        .getJson<Map<String, dynamic>>(versionPath, cancelToken: cancelToken);
    return ServerVersionDto.fromJson(json);
  }

  Future<HealthStatusDto> fetchHealth({Object? cancelToken}) async {
    final Map<String, dynamic> json = await _client
        .getJson<Map<String, dynamic>>(healthPath, cancelToken: cancelToken);
    return HealthStatusDto.fromJson(json);
  }
}
