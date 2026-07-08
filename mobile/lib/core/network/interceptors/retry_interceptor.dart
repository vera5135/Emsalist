import 'dart:async';

import 'package:dio/dio.dart';

/// Retries only idempotent GET requests on transient failures.
///
/// Policy:
/// - GET only; write methods are never retried automatically.
/// - Max 2 retries.
/// - Eligible: connection error, connect/send/receive timeout, and HTTP
///   429/502/503/504.
/// - Not eligible: cancellations and TLS/certificate errors.
/// - Honors a `Retry-After` header (seconds) when present.
class RetryInterceptor extends Interceptor {
  RetryInterceptor({
    required Dio dio,
    this.maxRetries = 2,
    this.baseDelay = const Duration(milliseconds: 300),
    Future<void> Function(Duration)? delay,
  }) : _dio = dio,
       _delay = delay ?? _defaultDelay;

  final Dio _dio;
  final int maxRetries;
  final Duration baseDelay;
  final Future<void> Function(Duration) _delay;

  static const String _attemptKey = 'retry_attempt';

  @override
  Future<void> onError(
    DioException err,
    ErrorInterceptorHandler handler,
  ) async {
    final RequestOptions options = err.requestOptions;
    final int attempt = (options.extra[_attemptKey] as int?) ?? 0;

    if (!_shouldRetry(err, attempt)) {
      handler.next(err);
      return;
    }

    final Duration wait = _retryAfter(err.response) ?? _backoff(attempt);
    await _delay(wait);

    if (options.cancelToken?.isCancelled ?? false) {
      handler.next(err);
      return;
    }

    options.extra[_attemptKey] = attempt + 1;
    try {
      final Response<dynamic> response = await _dio.fetch<dynamic>(options);
      handler.resolve(response);
    } on DioException catch (retryError) {
      handler.next(retryError);
    }
  }

  bool _shouldRetry(DioException err, int attempt) {
    if (attempt >= maxRetries) {
      return false;
    }
    if (err.requestOptions.method.toUpperCase() != 'GET') {
      return false;
    }
    switch (err.type) {
      case DioExceptionType.cancel:
      case DioExceptionType.badCertificate:
        return false;
      case DioExceptionType.connectionTimeout:
      case DioExceptionType.sendTimeout:
      case DioExceptionType.receiveTimeout:
      case DioExceptionType.transformTimeout:
      case DioExceptionType.connectionError:
        return true;
      case DioExceptionType.badResponse:
        final int? status = err.response?.statusCode;
        return status == 429 || status == 502 || status == 503 || status == 504;
      case DioExceptionType.unknown:
        return !_isSecurity(err);
    }
  }

  static bool _isSecurity(DioException err) {
    final String text = err.error?.toString().toLowerCase() ?? '';
    return text.contains('certificate') ||
        text.contains('handshake') ||
        text.contains('tls') ||
        text.contains('ssl');
  }

  Duration _backoff(int attempt) {
    return Duration(milliseconds: baseDelay.inMilliseconds * (attempt + 1));
  }

  Duration? _retryAfter(Response<dynamic>? response) {
    final String? value = response?.headers.value('retry-after');
    if (value == null) {
      return null;
    }
    final int? seconds = int.tryParse(value.trim());
    if (seconds == null || seconds < 0) {
      return null;
    }
    return Duration(seconds: seconds);
  }

  static Future<void> _defaultDelay(Duration duration) =>
      Future<void>.delayed(duration);
}
