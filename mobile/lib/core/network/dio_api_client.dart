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
    List<Interceptor> Function(Dio dio)? authInterceptors,
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
    _dio.interceptors.add(CorrelationInterceptor());
    // Auth (token inject) + refresh (401 rotation) run before retry/logging so
    // a refreshed request is retried with the new token.
    if (authInterceptors != null) {
      _dio.interceptors.addAll(authInterceptors(_dio));
    }
    _dio.interceptors.addAll(<Interceptor>[
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

  @override
  Future<T> postJson<T>(
    String path, {
    Object? body,
    Map<String, dynamic>? queryParameters,
    Object? cancelToken,
    Duration? receiveTimeout,
  }) async {
    try {
      final Response<dynamic> response = await _dio.post<dynamic>(
        path,
        data: body,
        queryParameters: queryParameters,
        cancelToken: cancelToken is CancelToken ? cancelToken : null,
        options: receiveTimeout == null
            ? null
            : Options(receiveTimeout: receiveTimeout),
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

  @override
  Future<T> patchJson<T>(
    String path, {
    Object? body,
    Object? cancelToken,
  }) async {
    try {
      final Response<dynamic> response = await _dio.patch<dynamic>(
        path,
        data: body,
        cancelToken: cancelToken is CancelToken ? cancelToken : null,
      );
      if (response.data is T) return response.data as T;
      throw _errorMapper.unexpected();
    } on DioException catch (error) {
      throw _errorMapper.fromDioException(error);
    } on ApiException {
      rethrow;
    } on Object {
      throw _errorMapper.unexpected();
    }
  }

  @override
  Future<T> deleteJson<T>(String path, {Object? cancelToken}) async {
    try {
      final Response<dynamic> response = await _dio.delete<dynamic>(
        path,
        cancelToken: cancelToken is CancelToken ? cancelToken : null,
      );
      final dynamic data = response.data;
      if (data is T) {
        return data;
      }
      if (<Map<String, dynamic>>[] is List<T>) {
        // Callers requesting Map for 204 get an empty map.
      }
      return <String, dynamic>{} as T;
    } on DioException catch (error) {
      throw _errorMapper.fromDioException(error);
    } on ApiException {
      rethrow;
    } on Object {
      throw _errorMapper.unexpected();
    }
  }

  @override
  Future<T> uploadBytes<T>(
    String path, {
    required List<int> bytes,
    required String filename,
    String? mimeType,
    Map<String, String> fields = const <String, String>{},
    Object? cancelToken,
  }) async {
    try {
      final FormData formData = FormData.fromMap(<String, dynamic>{
        ...fields,
        'file': MultipartFile.fromBytes(
          bytes,
          filename: filename,
          contentType: mimeType != null ? DioMediaType.parse(mimeType) : null,
        ),
      });
      final Response<dynamic> response = await _dio.post<dynamic>(
        path,
        data: formData,
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
