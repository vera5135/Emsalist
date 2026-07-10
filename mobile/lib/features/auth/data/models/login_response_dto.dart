import 'package:json_annotation/json_annotation.dart';

import 'user_info_dto.dart';

part 'login_response_dto.g.dart';

/// Mirrors backend `LoginResponse` (also returned by `/auth/apple/link`).
@JsonSerializable(createToJson: false)
class LoginResponseDto {
  const LoginResponseDto({
    required this.accessToken,
    this.refreshToken,
    this.tokenType = 'bearer',
    this.expiresIn,
    this.refreshExpiresIn,
    this.user,
  });

  @JsonKey(name: 'access_token')
  final String accessToken;

  @JsonKey(name: 'refresh_token')
  final String? refreshToken;

  @JsonKey(name: 'token_type')
  final String tokenType;

  @JsonKey(name: 'expires_in')
  final int? expiresIn;

  @JsonKey(name: 'refresh_expires_in')
  final int? refreshExpiresIn;

  final UserInfoDto? user;

  factory LoginResponseDto.fromJson(Map<String, dynamic> json) =>
      _$LoginResponseDtoFromJson(json);
}
