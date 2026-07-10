import 'package:dio/dio.dart';

import '../data/session_manager.dart';

/// Handles `401 Unauthorized` responses by performing a single-flight refresh
/// rotation and retrying the original request once.
///
/// - Only one refresh runs at a time (delegated to [SessionManager.refresh]);
///   parallel 401s await the same rotation.
/// - Each request is retried at most once (guarded by a private marker) so a
///   persistently-401 endpoint cannot loop.
/// - The refresh call itself and the login/refresh endpoints are never
///   retried here.
/// - On refresh failure the session is already cleared by [SessionManager];
///   the original 401 propagates so the UI can route to login.
class RefreshInterceptor extends Interceptor {
  RefreshInterceptor({required SessionManager sessionManager, required Dio dio})
    : _sessionManager = sessionManager,
      _dio = dio;

  final SessionManager _sessionManager;
  final Dio _dio;

  static const String _retriedFlag = 'x-auth-retried';
  static const String _refreshPath = '/api/v1/auth/refresh';

  bool _isAuthEndpoint(String path) {
    return path.endsWith(_refreshPath) || path.endsWith('/auth/login');
  }

  @override
  Future<void> onError(
    DioException err,
    ErrorInterceptorHandler handler,
  ) async {
    final RequestOptions request = err.requestOptions;
    final bool alreadyRetried = request.extra[_retriedFlag] == true;

    if (err.response?.statusCode != 401 ||
        alreadyRetried ||
        _isAuthEndpoint(request.path) ||
        !_sessionManager.hasSession) {
      handler.next(err);
      return;
    }

    final String? previous = _authTokenOf(request);
    final String? newToken = await _sessionManager.refresh(
      previousAccessToken: previous,
    );

    if (newToken == null || newToken.isEmpty) {
      // Session was cleared by the manager; surface the original error.
      handler.next(err);
      return;
    }

    try {
      final Options options = Options(
        method: request.method,
        headers: Map<String, dynamic>.from(request.headers)
          ..['Authorization'] = 'Bearer $newToken',
        responseType: request.responseType,
        contentType: request.contentType,
        sendTimeout: request.sendTimeout,
        receiveTimeout: request.receiveTimeout,
        extra: Map<String, dynamic>.from(request.extra)..[_retriedFlag] = true,
      );
      final Response<dynamic> response = await _dio.request<dynamic>(
        request.path,
        data: request.data,
        queryParameters: request.queryParameters,
        cancelToken: request.cancelToken,
        options: options,
      );
      handler.resolve(response);
    } on DioException catch (retryError) {
      handler.next(retryError);
    }
  }

  String? _authTokenOf(RequestOptions request) {
    final Object? header = request.headers['Authorization'];
    if (header is String && header.startsWith('Bearer ')) {
      return header.substring('Bearer '.length);
    }
    return null;
  }
}
