import 'package:dio/dio.dart';

import '../data/system/models/backend_error_envelope_dto.dart';
import 'api_exception.dart';

/// Maps Dio failures and backend error envelopes into UI-safe
/// [ApiException]s. Never leaks raw response bodies or stack traces.
class ErrorMapper {
  const ErrorMapper();

  static const String _genericMessage = 'Beklenmeyen bir hata oluştu.';
  static const String _networkMessage =
      'Bağlantı kurulamadı. İnternet bağlantınızı kontrol edin.';
  static const String _timeoutMessage = 'İstek zaman aşımına uğradı.';
  static const String _securityMessage = 'Güvenli bağlantı kurulamadı.';
  static const String _cancelledMessage = 'İstek iptal edildi.';

  ApiException fromDioException(DioException error) {
    switch (error.type) {
      case DioExceptionType.connectionTimeout:
      case DioExceptionType.sendTimeout:
      case DioExceptionType.receiveTimeout:
      case DioExceptionType.transformTimeout:
        return const ApiException(
          kind: ApiErrorKind.timeout,
          message: _timeoutMessage,
        );
      case DioExceptionType.cancel:
        return const ApiException(
          kind: ApiErrorKind.cancelled,
          message: _cancelledMessage,
        );
      case DioExceptionType.connectionError:
        return const ApiException(
          kind: ApiErrorKind.network,
          message: _networkMessage,
        );
      case DioExceptionType.badCertificate:
        return const ApiException(
          kind: ApiErrorKind.security,
          message: _securityMessage,
        );
      case DioExceptionType.badResponse:
        return _fromResponse(error.response);
      case DioExceptionType.unknown:
        if (_isSecurityError(error)) {
          return const ApiException(
            kind: ApiErrorKind.security,
            message: _securityMessage,
          );
        }
        return const ApiException(
          kind: ApiErrorKind.network,
          message: _networkMessage,
        );
    }
  }

  ApiException _fromResponse(Response<dynamic>? response) {
    final int? statusCode = response?.statusCode;
    final String? headerCorrelation = _correlationFromHeaders(response);
    final data = response?.data;

    String? code;
    String? message;
    String? correlationId = headerCorrelation;

    if (data is Map<String, dynamic>) {
      try {
        final BackendErrorDto? error = BackendErrorEnvelopeDto.fromJson(
          data,
        ).error;
        if (error != null) {
          code = error.code;
          message = error.message;
          correlationId = error.resolvedCorrelationId ?? correlationId;
        }
      } on Object {
        // Fall through to generic message; never surface parse internals.
      }
    }

    return ApiException(
      kind: ApiErrorKind.server,
      message: message ?? _messageForStatus(statusCode),
      statusCode: statusCode,
      code: code,
      correlationId: correlationId,
    );
  }

  ApiException unexpected({String? correlationId}) {
    return ApiException(
      kind: ApiErrorKind.unexpected,
      message: _genericMessage,
      correlationId: correlationId,
    );
  }

  static String? _correlationFromHeaders(Response<dynamic>? response) {
    final Headers? headers = response?.headers;
    if (headers == null) {
      return null;
    }
    return headers.value('x-correlation-id') ?? headers.value('x-request-id');
  }

  static bool _isSecurityError(DioException error) {
    final Object? inner = error.error;
    final String text = inner?.toString().toLowerCase() ?? '';
    return text.contains('certificate') ||
        text.contains('handshake') ||
        text.contains('tls') ||
        text.contains('ssl');
  }

  static String _messageForStatus(int? statusCode) {
    switch (statusCode) {
      case 400:
      case 422:
        return 'Geçersiz istek.';
      case 401:
        return 'Oturum gerekli veya geçersiz.';
      case 403:
        return 'Bu işlem için yetkiniz yok.';
      case 404:
        return 'Kaynak bulunamadı.';
      case 409:
        return 'İşlem çakışması oluştu.';
      case 429:
        return 'Çok fazla istek. Lütfen biraz sonra tekrar deneyin.';
      case 500:
        return 'Sunucu hatası oluştu.';
      case 502:
      case 503:
      case 504:
        return 'Servis geçici olarak kullanılamıyor.';
      default:
        return _genericMessage;
    }
  }
}
