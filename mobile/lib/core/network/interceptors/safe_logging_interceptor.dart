import 'dart:developer' as developer;

import 'package:dio/dio.dart';

/// Minimal request/response logger with strict redaction.
///
/// - Request/response bodies are logged only when [logBodies] is true
///   (development only). They are never logged in production builds.
/// - Sensitive headers (authorization, cookie, set-cookie, etc.) are never
///   logged in any environment.
class SafeLoggingInterceptor extends Interceptor {
  SafeLoggingInterceptor({
    this.enabled = false,
    this.logBodies = false,
    void Function(String)? sink,
  }) : _sink = sink ?? _defaultSink;

  final bool enabled;
  final bool logBodies;
  final void Function(String) _sink;

  static const Set<String> _sensitiveHeaders = <String>{
    'authorization',
    'cookie',
    'set-cookie',
    'proxy-authorization',
    'x-api-key',
  };

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    if (enabled) {
      _sink('→ ${options.method} ${options.uri}');
      _sink('  headers: ${_redactHeaders(options.headers)}');
      if (logBodies && options.data != null) {
        _sink('  body: ${options.data}');
      }
    }
    handler.next(options);
  }

  @override
  void onResponse(
    Response<dynamic> response,
    ResponseInterceptorHandler handler,
  ) {
    if (enabled) {
      _sink(
        '← ${response.statusCode} ${response.requestOptions.method} '
        '${response.requestOptions.uri}',
      );
      if (logBodies && response.data != null) {
        _sink('  body: ${response.data}');
      }
    }
    handler.next(response);
  }

  @override
  void onError(DioException err, ErrorInterceptorHandler handler) {
    if (enabled) {
      _sink(
        '✕ ${err.type.name} ${err.requestOptions.method} '
        '${err.requestOptions.uri} '
        'status=${err.response?.statusCode ?? '-'}',
      );
    }
    handler.next(err);
  }

  Map<String, String> _redactHeaders(Map<String, dynamic> headers) {
    final Map<String, String> safe = <String, String>{};
    headers.forEach((String key, dynamic value) {
      if (_sensitiveHeaders.contains(key.toLowerCase())) {
        safe[key] = '***';
      } else {
        safe[key] = value.toString();
      }
    });
    return safe;
  }

  static void _defaultSink(String message) {
    developer.log(message, name: 'api');
  }
}
