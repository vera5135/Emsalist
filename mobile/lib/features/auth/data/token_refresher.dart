import 'package:dio/dio.dart';

import '../../../core/config/api_config.dart';
import '../../../core/config/app_environment.dart';
import '../../../core/network/interceptors/correlation_interceptor.dart';
import '../../../core/network/interceptors/safe_logging_interceptor.dart';

/// Result of a successful refresh-token rotation.
class RefreshedTokens {
  const RefreshedTokens({required this.accessToken, required this.refreshToken});

  final String accessToken;
  final String refreshToken;
}

/// Performs the refresh-token rotation call.
///
/// Intentionally isolated from the authenticated [ApiClient] so it can never be
/// intercepted by the auth/refresh interceptors (which would recurse). Returns
/// `null` on any failure — callers treat that as "session no longer valid".
abstract class TokenRefresher {
  Future<RefreshedTokens?> refresh(String refreshToken);
}

/// [TokenRefresher] backed by a bare [Dio] with no auth/refresh interceptors.
class HttpTokenRefresher implements TokenRefresher {
  HttpTokenRefresher({required ApiConfig config, Dio? dio})
    : _dio = dio ?? _build(config);

  static const String refreshPath = '/api/v1/auth/refresh';

  final Dio _dio;

  static Dio _build(ApiConfig config) {
    final Dio dio = Dio();
    dio.options
      ..baseUrl = config.baseUrl
      ..connectTimeout = config.connectTimeout
      ..sendTimeout = config.sendTimeout
      ..receiveTimeout = config.receiveTimeout
      ..responseType = ResponseType.json
      ..headers['Accept'] = 'application/json';
    final bool isDev = config.environment == AppEnvironment.development;
    dio.interceptors.addAll(<Interceptor>[
      CorrelationInterceptor(),
      SafeLoggingInterceptor(enabled: isDev, logBodies: false),
    ]);
    return dio;
  }

  @override
  Future<RefreshedTokens?> refresh(String refreshToken) async {
    if (refreshToken.isEmpty) {
      return null;
    }
    try {
      final Response<dynamic> response = await _dio.post<dynamic>(
        refreshPath,
        data: <String, dynamic>{'refresh_token': refreshToken},
      );
      final dynamic data = response.data;
      if (data is! Map<String, dynamic>) {
        return null;
      }
      final Object? access = data['access_token'];
      final Object? refresh = data['refresh_token'];
      if (access is! String ||
          access.isEmpty ||
          refresh is! String ||
          refresh.isEmpty) {
        return null;
      }
      return RefreshedTokens(accessToken: access, refreshToken: refresh);
    } on Object {
      return null;
    }
  }
}
