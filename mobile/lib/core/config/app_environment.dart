import 'dart:io' show Platform;

/// Deployment environment (native flavor) the app runs against.
enum AppEnvironment {
  development,
  staging,
  production;

  /// Parses the `APP_ENVIRONMENT` dart-define value.
  ///
  /// Falls back to [AppEnvironment.development] when the value is empty and
  /// throws [ArgumentError] for an unrecognized non-empty value so build
  /// misconfiguration fails loudly during development.
  static AppEnvironment parse(String raw) {
    final String value = raw.trim().toLowerCase();
    if (value.isEmpty) {
      return AppEnvironment.development;
    }
    switch (value) {
      case 'development':
      case 'dev':
        return AppEnvironment.development;
      case 'staging':
      case 'stage':
        return AppEnvironment.staging;
      case 'production':
      case 'prod':
        return AppEnvironment.production;
      default:
        throw ArgumentError.value(
          raw,
          'APP_ENVIRONMENT',
          'Unknown environment. Expected development, staging, or production.',
        );
    }
  }

  /// The environment selected at build time via
  /// `--dart-define=APP_ENVIRONMENT=<value>`.
  static AppEnvironment current() => parse(_rawEnvironment);

  static const String _rawEnvironment = String.fromEnvironment(
    'APP_ENVIRONMENT',
    defaultValue: 'development',
  );

  bool get isDevelopment => this == AppEnvironment.development;
  bool get isStaging => this == AppEnvironment.staging;
  bool get isProduction => this == AppEnvironment.production;

  String get label {
    switch (this) {
      case AppEnvironment.development:
        return 'Development';
      case AppEnvironment.staging:
        return 'Staging';
      case AppEnvironment.production:
        return 'Production';
    }
  }
}

/// Abstraction over host platform detection so tests can inject a fake.
abstract class PlatformInfo {
  const PlatformInfo();

  bool get isAndroid;

  static const PlatformInfo system = _SystemPlatformInfo();
}

class _SystemPlatformInfo extends PlatformInfo {
  const _SystemPlatformInfo();

  @override
  bool get isAndroid {
    try {
      return Platform.isAndroid;
    } on Object {
      return false;
    }
  }
}

/// A [PlatformInfo] with an explicit value, for tests and non-IO targets.
class StaticPlatformInfo extends PlatformInfo {
  const StaticPlatformInfo({required bool isAndroid}) : _isAndroid = isAndroid;

  final bool _isAndroid;

  @override
  bool get isAndroid => _isAndroid;
}
