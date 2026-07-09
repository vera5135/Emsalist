import 'package:json_annotation/json_annotation.dart';

part 'health_status_dto.g.dart';

/// Response of `GET /health`.
///
/// `status` is one of `healthy`, `degraded`, `unhealthy`. When unhealthy the
/// backend returns HTTP 503 with this same body.
@JsonSerializable(createToJson: false)
class HealthStatusDto {
  const HealthStatusDto({
    this.status,
    this.service,
    this.checks,
    this.components,
  });

  final String? status;
  final String? service;
  final Map<String, dynamic>? checks;
  final Map<String, dynamic>? components;

  factory HealthStatusDto.fromJson(Map<String, dynamic> json) =>
      _$HealthStatusDtoFromJson(json);
}
