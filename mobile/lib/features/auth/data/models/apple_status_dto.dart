import 'package:json_annotation/json_annotation.dart';

part 'apple_status_dto.g.dart';

/// Mirrors backend `AppleStatusResponse`.
@JsonSerializable(createToJson: false)
class AppleStatusDto {
  const AppleStatusDto({required this.linked, required this.provider});

  final bool linked;
  final String provider;

  factory AppleStatusDto.fromJson(Map<String, dynamic> json) =>
      _$AppleStatusDtoFromJson(json);
}
