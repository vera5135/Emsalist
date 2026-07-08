import 'package:json_annotation/json_annotation.dart';

part 'server_version_dto.g.dart';

/// Response of `GET /api/v1/meta/version`.
@JsonSerializable(createToJson: false)
class ServerVersionDto {
  const ServerVersionDto({
    this.application,
    this.version,
    this.apiVersion,
    this.commit,
    this.buildTimestamp,
    this.environment,
  });

  final String? application;
  final String? version;

  @JsonKey(name: 'api_version')
  final String? apiVersion;

  final String? commit;

  @JsonKey(name: 'build_timestamp')
  final String? buildTimestamp;

  final String? environment;

  factory ServerVersionDto.fromJson(Map<String, dynamic> json) =>
      _$ServerVersionDtoFromJson(json);
}
