// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'apple_login_response_dto.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

AppleLoginResponseDto _$AppleLoginResponseDtoFromJson(
  Map<String, dynamic> json,
) => AppleLoginResponseDto(
  state: json['state'] as String?,
  accessToken: json['access_token'] as String?,
  refreshToken: json['refresh_token'] as String?,
  tokenType: json['token_type'] as String? ?? 'bearer',
  expiresIn: (json['expires_in'] as num?)?.toInt(),
  refreshExpiresIn: (json['refresh_expires_in'] as num?)?.toInt(),
  user: json['user'] == null
      ? null
      : UserInfoDto.fromJson(json['user'] as Map<String, dynamic>),
  linkTicket: json['link_ticket'] as String?,
  linkExpiresIn: (json['link_expires_in'] as num?)?.toInt(),
);
