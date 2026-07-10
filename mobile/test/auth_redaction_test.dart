import 'package:dio/dio.dart';
import 'package:emsalist_mobile/core/network/interceptors/safe_logging_interceptor.dart';
import 'package:emsalist_mobile/features/auth/domain/auth_session.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('token / log redaction', () {
    test('AuthSession.toString never contains token values', () {
      const AuthSession session = AuthSession(
        accessToken: 'SUPER-SECRET-ACCESS',
        refreshToken: 'SUPER-SECRET-REFRESH',
        userId: 'u1',
        tenant: 't1',
        role: 'lawyer',
      );

      final String text = session.toString();

      expect(text.contains('SUPER-SECRET-ACCESS'), isFalse);
      expect(text.contains('SUPER-SECRET-REFRESH'), isFalse);
      expect(text.contains('<redacted>'), isTrue);
      // Non-sensitive identity metadata may appear.
      expect(text.contains('u1'), isTrue);
    });

    test('SafeLoggingInterceptor redacts the Authorization header', () {
      final List<String> logs = <String>[];
      final SafeLoggingInterceptor interceptor = SafeLoggingInterceptor(
        enabled: true,
        logBodies: false,
        sink: logs.add,
      );
      final RequestOptions options = RequestOptions(
        path: '/api/v1/protected',
        headers: <String, dynamic>{
          'Authorization': 'Bearer SUPER-SECRET-ACCESS',
        },
      );

      interceptor.onRequest(options, RequestInterceptorHandler());

      final String joined = logs.join('\n');
      expect(joined.contains('SUPER-SECRET-ACCESS'), isFalse);
      expect(joined.contains('***'), isTrue);
    });

    test('SafeLoggingInterceptor never logs request bodies when disabled', () {
      final List<String> logs = <String>[];
      final SafeLoggingInterceptor interceptor = SafeLoggingInterceptor(
        enabled: true,
        logBodies: false,
        sink: logs.add,
      );
      final RequestOptions options = RequestOptions(
        path: '/api/v1/auth/login',
        data: <String, dynamic>{'password': 'SECRET-PW'},
      );

      interceptor.onRequest(options, RequestInterceptorHandler());

      expect(logs.join('\n').contains('SECRET-PW'), isFalse);
    });
  });
}
