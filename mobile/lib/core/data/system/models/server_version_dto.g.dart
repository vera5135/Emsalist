// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'server_version_dto.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

ServerVersionDto _$ServerVersionDtoFromJson(Map<String, dynamic> json) =>
    ServerVersionDto(
      application: json['application'] as String?,
      version: json['version'] as String?,
      apiVersion: json['api_version'] as String?,
      commit: json['commit'] as String?,
      buildTimestamp: json['build_timestamp'] as String?,
      environment: json['environment'] as String?,
    );
