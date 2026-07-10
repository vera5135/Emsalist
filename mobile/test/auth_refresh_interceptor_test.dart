import 'dart:async';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:emsalist_mobile/features/auth/data/refresh_interceptor.dart';
import 'package:emsalist_mobile/features/auth/data/session_manager.dart';
import 'package:emsalist_mobile/features/auth/data/token_refresher.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/auth_test_support.dart';

/// Adapter returning queued status codes in order; records Authorization
/// headers seen so we can assert the retried request used the new token.
class _SeqAdapter implements HttpClientAdapter {
  _SeqAdapter(this._statuses);

  final List<int> _statuses;
  int calls = 0;
  final List<String?> authHeaders = <String?>[];

  @override
  void close({bool force = false}) {}

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    authHeaders.add(options.headers['Authorization'] as String?);
    final int status = _statuses[calls.clamp(0, _statuses.length - 1)];
    calls++;
    if (status == 401) {
      throw DioException(
        requestOptions: options,
        type: DioExceptionType.badResponse,
        response: Response<dynamic>(requestOptions: options, statusCode: 401),
      );
    }
    return ResponseBody.fromString(
      '{}',
      status,
      headers: <String, List<String>>{
        Headers.contentTypeHeader: <String>[Headers.jsonContentType],
      },
    );
  }
}

class _FixedRefresher implements TokenRefresher {
  _FixedRefresher(this.result);
  final RefreshedTokens? result;
  int calls = 0;

  @override
  Future<RefreshedTokens?> refresh(String refreshToken) async {
    calls++;
    return result;
  }
}

Dio _dio(_SeqAdapter adapter, SessionManager manager) {
  final Dio dio = Dio(BaseOptions(baseUrl: 'http://localhost:8000'));
  dio.httpClientAdapter = adapter;
  // Simulate AuthInterceptor by injecting current token before each request.
  dio.interceptors.add(
    InterceptorsWrapper(
      onRequest: (RequestOptions options, RequestInterceptorHandler handler) {
        final String? token = manager.accessToken;
        if (token != null && token.isNotEmpty) {
          options.headers['Authorization'] = 'Bearer $token';
        }
        handler.next(options);
      },
    ),
  );
  dio.interceptors.add(RefreshInterceptor(sessionManager: manager, dio: dio));
  return dio;
}

void main() {
  test('401 triggers refresh and retries once with the new token', () async {
    final FakeSecureSessionStore store = FakeSecureSessionStore(kTestSession);
    final SessionManager manager = SessionManager(
      store: store,
      refresher: _FixedRefresher(
        const RefreshedTokens(accessToken: 'fresh', refreshToken: 'fresh-ref'),
      ),
    );
    await manager.restore();
    final _SeqAdapter adapter = _SeqAdapter(<int>[401, 200]);
    final Dio dio = _dio(adapter, manager);

    final Response<dynamic> res = await dio.get<dynamic>('/api/v1/protected');

    expect(res.statusCode, 200);
    expect(adapter.calls, 2);
    // Retried request carried the rotated token.
    expect(adapter.authHeaders.last, 'Bearer fresh');
  });

  test('does not loop when refresh keeps yielding 401', () async {
    final FakeSecureSessionStore store = FakeSecureSessionStore(kTestSession);
    final SessionManager manager = SessionManager(
      store: store,
      refresher: _FixedRefresher(
        const RefreshedTokens(accessToken: 'fresh', refreshToken: 'fresh-ref'),
      ),
    );
    await manager.restore();
    // Always 401: original + one retry, then it must give up.
    final _SeqAdapter adapter = _SeqAdapter(<int>[401, 401, 401, 401]);
    final Dio dio = _dio(adapter, manager);

    await expectLater(
      dio.get<dynamic>('/api/v1/protected'),
      throwsA(isA<DioException>()),
    );
    // Exactly 2 attempts: initial + single retry (no infinite loop).
    expect(adapter.calls, 2);
  });

  test('failed refresh clears session and surfaces original 401', () async {
    final FakeSecureSessionStore store = FakeSecureSessionStore(kTestSession);
    bool cleared = false;
    final SessionManager manager = SessionManager(
      store: store,
      refresher: _FixedRefresher(null),
      onSessionCleared: () => cleared = true,
    );
    await manager.restore();
    final _SeqAdapter adapter = _SeqAdapter(<int>[401]);
    final Dio dio = _dio(adapter, manager);

    await expectLater(
      dio.get<dynamic>('/api/v1/protected'),
      throwsA(isA<DioException>()),
    );
    expect(cleared, isTrue);
    expect(manager.hasSession, isFalse);
    // Only the original attempt; no retry after refresh failed.
    expect(adapter.calls, 1);
  });

  test('does not attempt refresh when no session exists', () async {
    final FakeSecureSessionStore store = FakeSecureSessionStore();
    final _FixedRefresher refresher = _FixedRefresher(
      const RefreshedTokens(accessToken: 'x', refreshToken: 'y'),
    );
    final SessionManager manager = SessionManager(
      store: store,
      refresher: refresher,
    );
    await manager.restore(); // null
    final _SeqAdapter adapter = _SeqAdapter(<int>[401]);
    final Dio dio = _dio(adapter, manager);

    await expectLater(
      dio.get<dynamic>('/api/v1/protected'),
      throwsA(isA<DioException>()),
    );
    expect(refresher.calls, 0);
    expect(adapter.calls, 1);
  });
}
