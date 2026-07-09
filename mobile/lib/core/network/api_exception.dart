/// Categorizes a failure so the UI and retry policy can react consistently.
enum ApiErrorKind {
  /// No connectivity / DNS / socket failure before a response was received.
  network,

  /// The request exceeded a configured timeout.
  timeout,

  /// The request was cancelled by the caller.
  cancelled,

  /// TLS / certificate validation failure.
  security,

  /// The server returned a structured error response.
  server,

  /// The response could not be parsed or was otherwise malformed.
  unexpected,
}

/// A typed, UI-safe error surfaced by the network layer.
///
/// Never carries raw stack traces or raw response bodies. The optional
/// [correlationId] can be shown to the user for support.
class ApiException implements Exception {
  const ApiException({
    required this.kind,
    required this.message,
    this.statusCode,
    this.code,
    this.correlationId,
  });

  final ApiErrorKind kind;

  /// A short, user-safe message.
  final String message;

  /// HTTP status code when a response was received.
  final int? statusCode;

  /// Machine-readable backend error code (e.g. `RESOURCE_NOT_FOUND`).
  final String? code;

  /// Correlation id from the response, useful for support.
  final String? correlationId;

  bool get isRetryable {
    switch (kind) {
      case ApiErrorKind.network:
      case ApiErrorKind.timeout:
        return true;
      case ApiErrorKind.server:
        return statusCode == 429 ||
            statusCode == 502 ||
            statusCode == 503 ||
            statusCode == 504;
      case ApiErrorKind.cancelled:
      case ApiErrorKind.security:
      case ApiErrorKind.unexpected:
        return false;
    }
  }

  @override
  String toString() =>
      'ApiException(kind: $kind, statusCode: $statusCode, code: $code)';
}
