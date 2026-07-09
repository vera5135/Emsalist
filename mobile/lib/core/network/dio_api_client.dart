import 'package:dio/dio.dart';

import '../config/api_config.dart';
import '../config/app_environment.dart';
import 'api_client.dart';
import 'api_exception.dart';
import 'error_mapper.dart';
import 'interceptors/correlation_interceptor.dart';
import 'interceptors/retry_interceptor.dart';
import 'interceptors/safe_logging_interceptor.dart';

/// Dio-backed [ApiClient].
///
/// Timeouts, correlation, resilient retry and safe logging are configured
/// once here. Logging bodies is enabled only in development.
class DioApiClient implements ApiClient {
  DioApiClient({
    required ApiConfig config,
    Dio? dio,
    ErrorMapper errorMapper = const ErrorMapper(),
  }) : _errorMapper = errorMapper,
       _dio = dio ?? Dio() {
    _dio.options
      ..baseUrl = config.baseUrl
      ..connectTimeout = config.connectTimeout
      ..sendTimeout = config.sendTimeout
      ..receiveTimeout = config.receiveTimeout
      ..responseType = ResponseType.json
      ..headers['Accept'] = 'application/json';

    final bool isDev = config.environment == AppEnvironment.development;
    _dio.interceptors.addAll(<Interceptor>[
      CorrelationInterceptor(),
      RetryInterceptor(dio: _dio),
      SafeLoggingInterceptor(enabled: isDev, logBodies: isDev),
    ]);
  }

  final Dio _dio;
  final ErrorMapper _errorMapper;

  @override
  Future<T> getJson<T>(
    String path, {
    Map<String, dynamic>? queryParameters,
    Object? cancelToken,
  }) async {
    try {
      final Response<dynamic> response = await _dio.get<dynamic>(
        path,
        queryParameters: queryParameters,
        cancelToken: cancelToken is CancelToken ? cancelToken : null,
      );
      final dynamic data = response.data;
      if (data is T) {
        return data;
      }
      throw _errorMapper.unexpected();
    } on DioException catch (error) {
      throw _errorMapper.fromDioException(error);
    } on ApiException {
      rethrow;
    } on Object {
      throw _errorMapper.unexpected();
    }
  }
}
