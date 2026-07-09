import 'package:dio/dio.dart';
import 'package:emsalist_mobile/core/data/system/models/backend_error_envelope_dto.dart';
import 'package:emsalist_mobile/core/data/system/models/health_status_dto.dart';
import 'package:emsalist_mobile/core/data/system/models/server_version_dto.dart';
import 'package:emsalist_mobile/core/network/api_exception.dart';
import 'package:emsalist_mobile/core/network/error_mapper.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  const ErrorMapper mapper = ErrorMapper();
  final RequestOptions options = RequestOptions(path: '/api/v1/meta/version');

  group('ErrorMapper Dio types', () {
    test('connection timeout maps to timeout kind', () {
      final ApiException e = mapper.fromDioException(
        DioException(
          requestOptions: options,
          type: DioExceptionType.connectionTimeout,
        ),
      );
      expect(e.kind, ApiErrorKind.timeout);
      expect(e.isRetryable, isTrue);
    });

    test('connection error maps to network kind', () {
      final ApiException e = mapper.fromDioException(
        DioException(
          requestOptions: options,
          type: DioExceptionType.connectionError,
        ),
      );
      expect(e.kind, ApiErrorKind.network);
      expect(e.isRetryable, isTrue);
    });

    test('cancel maps to cancelled and is not retryable', () {
      final ApiException e = mapper.fromDioException(
        DioException(requestOptions: options, type: DioExceptionType.cancel),
      );
      expect(e.kind, ApiErrorKind.cancelled);
      expect(e.isRetryable, isFalse);
    });

    test('bad certificate maps to security and is not retryable', () {
      final ApiException e = mapper.fromDioException(
        DioException(
          requestOptions: options,
          type: DioExceptionType.badCertificate,
        ),
      );
      expect(e.kind, ApiErrorKind.security);
      expect(e.isRetryable, isFalse);
    });
  });

  group('ErrorMapper backend envelope', () {
    test('parses correlation_id and code from envelope', () {
      final ApiException e = mapper.fromDioException(
        DioException(
          requestOptions: options,
          type: DioExceptionType.badResponse,
          response: Response<dynamic>(
            requestOptions: options,
            statusCode: 404,
            data: <String, dynamic>{
              'error': <String, dynamic>{
                'code': 'RESOURCE_NOT_FOUND',
                'message': 'Kaynak bulunamadı.',
                'correlation_id': 'corr-123',
              },
            },
          ),
        ),
      );
      expect(e.kind, ApiErrorKind.server);
      expect(e.statusCode, 404);
      expect(e.code, 'RESOURCE_NOT_FOUND');
      expect(e.message, 'Kaynak bulunamadı.');
      expect(e.correlationId, 'corr-123');
      expect(e.isRetryable, isFalse);
    });

    test('request_id is used as correlation fallback', () {
      final ApiException e = mapper.fromDioException(
        DioException(
          requestOptions: options,
          type: DioExceptionType.badResponse,
          response: Response<dynamic>(
            requestOptions: options,
            statusCode: 500,
            data: <String, dynamic>{
              'error': <String, dynamic>{
                'code': 'INTERNAL_ERROR',
                'message': 'Sunucu hatası',
                'request_id': 'req-789',
              },
            },
          ),
        ),
      );
      expect(e.correlationId, 'req-789');
    });

    test('503 server error is retryable', () {
      final ApiException e = mapper.fromDioException(
        DioException(
          requestOptions: options,
          type: DioExceptionType.badResponse,
          response: Response<dynamic>(
            requestOptions: options,
            statusCode: 503,
            data: const <String, dynamic>{},
          ),
        ),
      );
      expect(e.statusCode, 503);
      expect(e.isRetryable, isTrue);
    });

    test('falls back to correlation header when body has no id', () {
      final ApiException e = mapper.fromDioException(
        DioException(
          requestOptions: options,
          type: DioExceptionType.badResponse,
          response: Response<dynamic>(
            requestOptions: options,
            statusCode: 400,
            headers: Headers.fromMap(<String, List<String>>{
              'x-correlation-id': <String>['hdr-1'],
            }),
            data: const <String, dynamic>{},
          ),
        ),
      );
      expect(e.correlationId, 'hdr-1');
    });
  });

  group('BackendErrorDto', () {
    test('resolvedCorrelationId prefers correlation_id', () {
      const BackendErrorDto dto = BackendErrorDto(
        correlationId: 'a',
        requestId: 'b',
      );
      expect(dto.resolvedCorrelationId, 'a');
    });

    test('resolvedCorrelationId falls back to request_id', () {
      const BackendErrorDto dto = BackendErrorDto(requestId: 'b');
      expect(dto.resolvedCorrelationId, 'b');
    });
  });

  group('DTO JSON parsing', () {
    test('ServerVersionDto parses real field names', () {
      final ServerVersionDto dto = ServerVersionDto.fromJson(<String, dynamic>{
        'application': 'emsalist',
        'version': '0.1.0',
        'api_version': 'v1',
        'commit': 'abc123',
        'build_timestamp': '2026-07-08T00:00:00Z',
        'environment': 'development',
      });
      expect(dto.application, 'emsalist');
      expect(dto.version, '0.1.0');
      expect(dto.apiVersion, 'v1');
      expect(dto.commit, 'abc123');
      expect(dto.environment, 'development');
    });

    test('HealthStatusDto parses status and nested maps', () {
      final HealthStatusDto dto = HealthStatusDto.fromJson(<String, dynamic>{
        'status': 'healthy',
        'service': 'emsalist-api',
        'checks': <String, dynamic>{
          'database': <String, dynamic>{'status': 'ok'},
        },
        'components': <String, dynamic>{},
      });
      expect(dto.status, 'healthy');
      expect(dto.service, 'emsalist-api');
      expect(dto.checks, isNotNull);
    });

    test('BackendErrorEnvelopeDto tolerates missing error', () {
      final BackendErrorEnvelopeDto dto = BackendErrorEnvelopeDto.fromJson(
        const <String, dynamic>{},
      );
      expect(dto.error, isNull);
    });
  });
}
