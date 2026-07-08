// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'health_status_dto.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

HealthStatusDto _$HealthStatusDtoFromJson(Map<String, dynamic> json) =>
    HealthStatusDto(
      status: json['status'] as String?,
      service: json['service'] as String?,
      checks: json['checks'] as Map<String, dynamic>?,
      components: json['components'] as Map<String, dynamic>?,
    );
