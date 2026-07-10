import '../../../core/network/api_client.dart';
import 'models/apple_login_response_dto.dart';
import 'models/apple_status_dto.dart';
import 'models/login_response_dto.dart';

/// Thin data source for the backend authentication endpoints.
///
/// All calls go through the authenticated [ApiClient]; the auth/refresh
/// interceptors attach the Bearer token and rotate on 401 where relevant.
/// Endpoints that must run unauthenticated (login, apple/login, apple/link)
/// simply carry no token because none is set at that point.
class AuthApi {
  const AuthApi(this._client);

  final ApiClient _client;

  static const String loginPath = '/api/v1/auth/login';
  static const String refreshPath = '/api/v1/auth/refresh';
  static const String logoutPath = '/api/v1/auth/logout';
  static const String appleLoginPath = '/api/v1/auth/apple/login';
  static const String appleLinkPath = '/api/v1/auth/apple/link';
  static const String appleStatusPath = '/api/v1/auth/apple/status';
  static const String appleUnlinkPath = '/api/v1/auth/apple/unlink';

  Future<LoginResponseDto> login({
    required String email,
    required String password,
    Object? cancelToken,
  }) async {
    final Map<String, dynamic> json = await _client
        .postJson<Map<String, dynamic>>(
          loginPath,
          body: <String, dynamic>{'email': email, 'password': password},
          cancelToken: cancelToken,
        );
    return LoginResponseDto.fromJson(json);
  }

  Future<AppleLoginResponseDto> appleLogin({
    required String authorizationCode,
    required String rawNonce,
    Object? cancelToken,
  }) async {
    final Map<String, dynamic> json = await _client
        .postJson<Map<String, dynamic>>(
          appleLoginPath,
          body: <String, dynamic>{
            'authorization_code': authorizationCode,
            'raw_nonce': rawNonce,
          },
          cancelToken: cancelToken,
        );
    return AppleLoginResponseDto.fromJson(json);
  }

  Future<LoginResponseDto> appleLink({
    required String linkTicket,
    required String email,
    required String password,
    Object? cancelToken,
  }) async {
    final Map<String, dynamic> json = await _client
        .postJson<Map<String, dynamic>>(
          appleLinkPath,
          body: <String, dynamic>{
            'link_ticket': linkTicket,
            'email': email,
            'password': password,
          },
          cancelToken: cancelToken,
        );
    return LoginResponseDto.fromJson(json);
  }

  Future<AppleStatusDto> appleStatus({Object? cancelToken}) async {
    final Map<String, dynamic> json = await _client
        .getJson<Map<String, dynamic>>(
          appleStatusPath,
          cancelToken: cancelToken,
        );
    return AppleStatusDto.fromJson(json);
  }

  Future<void> appleUnlink({
    required String currentPassword,
    Object? cancelToken,
  }) async {
    await _client.postJson<Map<String, dynamic>>(
      appleUnlinkPath,
      body: <String, dynamic>{'current_password': currentPassword},
      cancelToken: cancelToken,
    );
  }

  Future<void> logout({Object? cancelToken}) async {
    await _client.postJson<Map<String, dynamic>>(
      logoutPath,
      cancelToken: cancelToken,
    );
  }
}
