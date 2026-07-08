/// Thrown when the API configuration is incomplete or invalid for the
/// current environment.
///
/// For staging and production the base URL must be supplied at build time via
/// `--dart-define=API_BASE_URL=...`. When it is missing the app fails closed
/// (no network call is attempted against a fabricated host).
class ApiConfigurationException implements Exception {
  const ApiConfigurationException(this.message, {this.environment});

  final String message;
  final String? environment;

  @override
  String toString() {
    if (environment == null) {
      return 'ApiConfigurationException: $message';
    }
    return 'ApiConfigurationException($environment): $message';
  }
}
