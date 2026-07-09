// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'backend_error_envelope_dto.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

BackendErrorEnvelopeDto _$BackendErrorEnvelopeDtoFromJson(
  Map<String, dynamic> json,
) => BackendErrorEnvelopeDto(
  error: json['error'] == null
      ? null
      : BackendErrorDto.fromJson(json['error'] as Map<String, dynamic>),
);

BackendErrorDto _$BackendErrorDtoFromJson(Map<String, dynamic> json) =>
    BackendErrorDto(
      code: json['code'] as String?,
      message: json['message'] as String?,
      correlationId: json['correlation_id'] as String?,
      requestId: json['request_id'] as String?,
    );
