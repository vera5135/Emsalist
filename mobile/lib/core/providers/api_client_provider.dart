import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../config/api_config.dart';
import '../data/system/system_api.dart';
import '../data/system/system_repository.dart';
import '../network/api_client.dart';
import '../network/dio_api_client.dart';

/// Resolves the [ApiConfig] for the active build environment.
///
/// May throw [ApiConfigurationException] for staging/production when
/// `API_BASE_URL` is missing; consumers should read this lazily and surface a
/// configuration error state instead of crashing.
final Provider<ApiConfig> apiConfigProvider = Provider<ApiConfig>((ref) {
  return ApiConfig.resolve();
});

final Provider<ApiClient> apiClientProvider = Provider<ApiClient>((ref) {
  final ApiConfig config = ref.watch(apiConfigProvider);
  return DioApiClient(config: config);
});

final Provider<SystemApi> systemApiProvider = Provider<SystemApi>((ref) {
  return SystemApi(ref.watch(apiClientProvider));
});

final Provider<SystemRepository> systemRepositoryProvider =
    Provider<SystemRepository>((ref) {
      return SystemRepository(ref.watch(systemApiProvider));
    });
