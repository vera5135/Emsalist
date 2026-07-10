import 'package:json_annotation/json_annotation.dart';

part 'user_info_dto.g.dart';

/// Mirrors backend `UserInfo`.
@JsonSerializable(createToJson: false)
class UserInfoDto {
  const UserInfoDto({this.id, this.tenant, this.role});

  final String? id;
  final String? tenant;
  final String? role;

  factory UserInfoDto.fromJson(Map<String, dynamic> json) =>
      _$UserInfoDtoFromJson(json);
}
