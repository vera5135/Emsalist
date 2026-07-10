import 'package:json_annotation/json_annotation.dart';

import 'user_info_dto.dart';

part 'apple_login_response_dto.g.dart';

/// Mirrors backend Apple login discriminated union response.
///
/// The backend returns either `state: "authenticated"` (with tokens+user, no
/// link ticket) or `state: "link_required"` (with link ticket, no tokens).
/// This single DTO parses both shapes; use [isAuthenticated] /
/// [isLinkRequired] to branch. The raw [linkTicket] is treated as an opaque
/// secret and is never shown to the user.
@JsonSerializable(createToJson: false)
class AppleLoginResponseDto {
  const AppleLoginResponseDto({
    this.state,
    this.accessToken,
    this.refreshToken,
    this.tokenType = 'bearer',
    this.expiresIn,
    this.refreshExpiresIn,
    this.user,
    this.linkTicket,
    this.linkExpiresIn,
  });

  final String? state;

  @JsonKey(name: 'access_token')
  final String? accessToken;

  @JsonKey(name: 'refresh_token')
  final String? refreshToken;

  @JsonKey(name: 'token_type')
  final String tokenType;

  @JsonKey(name: 'expires_in')
  final int? expiresIn;

  @JsonKey(name: 'refresh_expires_in')
  final int? refreshExpiresIn;

  final UserInfoDto? user;

  @JsonKey(name: 'link_ticket')
  final String? linkTicket;

  @JsonKey(name: 'link_expires_in')
  final int? linkExpiresIn;

  bool get isAuthenticated =>
      state == 'authenticated' && (accessToken?.isNotEmpty ?? false);

  bool get isLinkRequired =>
      state == 'link_required' && (linkTicket?.isNotEmpty ?? false);

  factory AppleLoginResponseDto.fromJson(Map<String, dynamic> json) =>
      _$AppleLoginResponseDtoFromJson(json);
}
