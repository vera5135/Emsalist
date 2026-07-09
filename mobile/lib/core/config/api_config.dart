import 'app_environment.dart';
import 'api_configuration_exception.dart';

/// Resolves the backend base URL and network timeouts for the active
/// [AppEnvironment].
///
/// Base URL resolution rules:
/// - An explicit `--dart-define=API_BASE_URL=...` always wins.
/// - Development falls back to a platform-aware localhost default
///   (`http://10.0.2.2:8000` on Android emulators, `http://localhost:8000`
///   elsewhere).
/// - Staging and production have no default: a missing base URL throws
///   [ApiConfigurationException] so the app fails closed instead of calling a
///   fabricated host.
class ApiConfig {
  const ApiConfig({
    required this.environment,
    required this.baseUrl,
    this.connectTimeout = const Duration(seconds: 10),
    this.sendTimeout = const Duration(seconds: 15),
    this.receiveTimeout = const Duration(seconds: 20),
  });

  final AppEnvironment environment;
  final String baseUrl;
  final Duration connectTimeout;
  final Duration sendTimeout;
  final Duration receiveTimeout;

  static const String _rawBaseUrl = String.fromEnvironment('API_BASE_URL');

  static const String androidEmulatorLocalhost = 'http://10.0.2.2:8000';
  static const String desktopLocalhost = 'http://localhost:8000';

  /// Builds the configuration for the current build environment.
  ///
  /// Throws [ApiConfigurationException] for staging/production when
  /// `API_BASE_URL` is not provided.
  factory ApiConfig.resolve({
    AppEnvironment? environment,
    String rawBaseUrl = _rawBaseUrl,
    PlatformInfo platform = PlatformInfo.system,
  }) {
    final AppEnvironment env = environment ?? AppEnvironment.current();
    final String explicit = rawBaseUrl.trim();

    if (explicit.isNotEmpty) {
      return ApiConfig(environment: env, baseUrl: _normalize(explicit));
    }

    switch (env) {
      case AppEnvironment.development:
        final String host = platform.isAndroid
            ? androidEmulatorLocalhost
            : desktopLocalhost;
        return ApiConfig(environment: env, baseUrl: host);
      case AppEnvironment.staging:
      case AppEnvironment.production:
        throw ApiConfigurationException(
          'API_BASE_URL must be provided for ${env.label} builds. '
          'Pass --dart-define=API_BASE_URL=https://...',
          environment: env.name,
        );
    }
  }

  static String _normalize(String url) {
    if (url.endsWith('/')) {
      return url.substring(0, url.length - 1);
    }
    return url;
  }
}
