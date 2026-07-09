import 'package:emsalist_mobile/core/config/api_config.dart';
import 'package:emsalist_mobile/core/config/api_configuration_exception.dart';
import 'package:emsalist_mobile/core/config/app_environment.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('AppEnvironment.parse', () {
    test('empty defaults to development', () {
      expect(AppEnvironment.parse(''), AppEnvironment.development);
      expect(AppEnvironment.parse('   '), AppEnvironment.development);
    });

    test('recognizes each environment case-insensitively', () {
      expect(AppEnvironment.parse('development'), AppEnvironment.development);
      expect(AppEnvironment.parse('DEV'), AppEnvironment.development);
      expect(AppEnvironment.parse('staging'), AppEnvironment.staging);
      expect(AppEnvironment.parse('Stage'), AppEnvironment.staging);
      expect(AppEnvironment.parse('production'), AppEnvironment.production);
      expect(AppEnvironment.parse('PROD'), AppEnvironment.production);
    });

    test('throws on unknown value', () {
      expect(() => AppEnvironment.parse('qa'), throwsA(isA<ArgumentError>()));
    });
  });

  group('ApiConfig.resolve', () {
    test('development uses android emulator host on android', () {
      final ApiConfig config = ApiConfig.resolve(
        environment: AppEnvironment.development,
        rawBaseUrl: '',
        platform: const StaticPlatformInfo(isAndroid: true),
      );
      expect(config.baseUrl, ApiConfig.androidEmulatorLocalhost);
    });

    test('development uses localhost host off android', () {
      final ApiConfig config = ApiConfig.resolve(
        environment: AppEnvironment.development,
        rawBaseUrl: '',
        platform: const StaticPlatformInfo(isAndroid: false),
      );
      expect(config.baseUrl, ApiConfig.desktopLocalhost);
    });

    test('explicit base url wins and trailing slash is trimmed', () {
      final ApiConfig config = ApiConfig.resolve(
        environment: AppEnvironment.production,
        rawBaseUrl: 'https://api.example.com/',
        platform: const StaticPlatformInfo(isAndroid: false),
      );
      expect(config.baseUrl, 'https://api.example.com');
    });

    test('staging without base url fails closed', () {
      expect(
        () => ApiConfig.resolve(
          environment: AppEnvironment.staging,
          rawBaseUrl: '',
          platform: const StaticPlatformInfo(isAndroid: false),
        ),
        throwsA(isA<ApiConfigurationException>()),
      );
    });

    test('production without base url fails closed', () {
      expect(
        () => ApiConfig.resolve(
          environment: AppEnvironment.production,
          rawBaseUrl: '',
          platform: const StaticPlatformInfo(isAndroid: true),
        ),
        throwsA(isA<ApiConfigurationException>()),
      );
    });

    test('timeouts are configured', () {
      final ApiConfig config = ApiConfig.resolve(
        environment: AppEnvironment.development,
        rawBaseUrl: 'http://localhost:8000',
        platform: const StaticPlatformInfo(isAndroid: false),
      );
      expect(config.connectTimeout, isNonZero);
      expect(config.sendTimeout, isNonZero);
      expect(config.receiveTimeout, isNonZero);
    });
  });
}

Matcher get isNonZero => predicate<Duration>(
  (Duration d) => d > Duration.zero,
  'is a non-zero duration',
);
