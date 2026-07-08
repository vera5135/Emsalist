import 'package:json_annotation/json_annotation.dart';

part 'backend_error_envelope_dto.g.dart';

/// Mirrors the backend error envelope:
/// `{"error": {"code": "...", "message": "...", "correlation_id": "..."}}`.
///
/// `request_id` is accepted only as a forward-compatibility fallback; the
/// current backend emits `correlation_id`.
@JsonSerializable(createToJson: false)
class BackendErrorEnvelopeDto {
  const BackendErrorEnvelopeDto({this.error});

  final BackendErrorDto? error;

  factory BackendErrorEnvelopeDto.fromJson(Map<String, dynamic> json) =>
      _$BackendErrorEnvelopeDtoFromJson(json);
}

@JsonSerializable(createToJson: false)
class BackendErrorDto {
  const BackendErrorDto({
    this.code,
    this.message,
    this.correlationId,
    this.requestId,
  });

  final String? code;
  final String? message;

  @JsonKey(name: 'correlation_id')
  final String? correlationId;

  @JsonKey(name: 'request_id')
  final String? requestId;

  /// Correlation id with request_id as a compatibility fallback.
  String? get resolvedCorrelationId => correlationId ?? requestId;

  factory BackendErrorDto.fromJson(Map<String, dynamic> json) =>
      _$BackendErrorDtoFromJson(json);
}
