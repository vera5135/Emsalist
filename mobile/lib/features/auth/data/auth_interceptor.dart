import 'package:dio/dio.dart';

import '../data/session_manager.dart';

/// Injects the current access token as a `Bearer` Authorization header on
/// outgoing requests when a session exists.
///
/// The token value is never logged here; [SafeLoggingInterceptor] redacts the
/// Authorization header everywhere.
class AuthInterceptor extends Interceptor {
  AuthInterceptor({required SessionManager sessionManager})
    : _sessionManager = sessionManager;

  final SessionManager _sessionManager;

  static const String _skipHeader = 'x-skip-auth';

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    if (options.headers.remove(_skipHeader) != null) {
      handler.next(options);
      return;
    }
    final String? token = _sessionManager.accessToken;
    if (token != null && token.isNotEmpty) {
      options.headers['Authorization'] = 'Bearer $token';
    }
    handler.next(options);
  }
}
