import '../../../core/network/api_exception.dart';
import '../domain/auth_session.dart';
import 'apple_credential_provider.dart';
import 'auth_api.dart';
import 'models/apple_login_response_dto.dart';
import 'models/login_response_dto.dart';

/// Outcome of an Apple sign-in attempt.
sealed class AppleSignInResult {
  const AppleSignInResult();
}

/// Apple identity matched an existing linked account; a session was issued.
class AppleAuthenticated extends AppleSignInResult {
  const AppleAuthenticated(this.session);
  final AuthSession session;
}

/// Apple identity is not linked yet; the user must confirm email + password.
///
/// The [linkTicket] is an opaque secret used only for the follow-up link call.
/// It is never surfaced to the user.
class AppleLinkRequired extends AppleSignInResult {
  const AppleLinkRequired(this.linkTicket);
  final String linkTicket;
}

/// The user cancelled the native Apple flow — no error should be shown.
class AppleSignInCancelled extends AppleSignInResult {
  const AppleSignInCancelled();
}

/// Domain-level authentication operations.
///
/// Translates transport DTOs into [AuthSession] / [AppleSignInResult] and never
/// leaks tokens or link tickets into logs or error messages.
class AuthRepository {
  const AuthRepository({
    required AuthApi api,
    required AppleCredentialProvider appleCredentialProvider,
  }) : _api = api,
       _apple = appleCredentialProvider;

  final AuthApi _api;
  final AppleCredentialProvider _apple;

  Future<bool> isAppleAvailable() => _apple.isAvailable();

  /// Email + password login. Throws [ApiException] on failure.
  Future<AuthSession> loginWithPassword({
    required String email,
    required String password,
  }) async {
    final LoginResponseDto dto = await _api.login(
      email: email.trim(),
      password: password,
    );
    return _sessionFromLogin(dto);
  }

  /// Runs the full Apple sign-in: raw nonce → native credential → backend
  /// exchange → branch on the discriminated union.
  Future<AppleSignInResult> signInWithApple() async {
    final String rawNonce = AppleNonce.generateRaw();
    final AppleCredential credential;
    try {
      credential = await _apple.getCredential(rawNonce: rawNonce);
    } on AppleCredentialException catch (e) {
      if (e.cancelled) {
        return const AppleSignInCancelled();
      }
      rethrow;
    }

    final AppleLoginResponseDto dto = await _api.appleLogin(
      authorizationCode: credential.authorizationCode,
      rawNonce: credential.rawNonce,
    );

    if (dto.isLinkRequired) {
      return AppleLinkRequired(dto.linkTicket!);
    }
    if (dto.isAuthenticated) {
      return AppleAuthenticated(
        AuthSession(
          accessToken: dto.accessToken!,
          refreshToken: dto.refreshToken ?? '',
          userId: dto.user?.id,
          tenant: dto.user?.tenant,
          role: dto.user?.role,
        ),
      );
    }
    // Unrecognized shape — fail closed as a generic server error.
    throw const ApiException(
      kind: ApiErrorKind.unexpected,
      message: 'Beklenmeyen bir hata oluştu.',
    );
  }

  /// Confirms email + existing password to link the pending Apple identity.
  /// Throws [ApiException] on failure (including expired/used ticket → 400).
  Future<AuthSession> linkApple({
    required String linkTicket,
    required String email,
    required String password,
  }) async {
    final LoginResponseDto dto = await _api.appleLink(
      linkTicket: linkTicket,
      email: email.trim(),
      password: password,
    );
    return _sessionFromLogin(dto);
  }

  Future<bool> appleLinkStatus() async {
    final dto = await _api.appleStatus();
    return dto.linked;
  }

  Future<void> unlinkApple({required String currentPassword}) {
    return _api.appleUnlink(currentPassword: currentPassword);
  }

  Future<void> logout() => _api.logout();

  AuthSession _sessionFromLogin(LoginResponseDto dto) {
    return AuthSession(
      accessToken: dto.accessToken,
      refreshToken: dto.refreshToken ?? '',
      userId: dto.user?.id,
      tenant: dto.user?.tenant,
      role: dto.user?.role,
    );
  }
}
