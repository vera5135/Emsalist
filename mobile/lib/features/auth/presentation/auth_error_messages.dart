import '../../../core/network/api_exception.dart';
import '../data/apple_credential_provider.dart';

/// Maps caught exceptions from auth flows into short, user-safe Turkish
/// messages. Never surfaces tokens, tickets, stack traces or raw bodies.
class AuthErrorMessages {
  const AuthErrorMessages._();

  static const String appleUnavailable =
      'Apple ile giriş şu anda kullanılamıyor. Lütfen e-posta ve parolanızla '
      'giriş yapın.';
  static const String linkTicketInvalid =
      'Apple bağlama oturumunuzun süresi doldu. Lütfen Apple ile girişi '
      'yeniden başlatın.';
  static const String invalidCredentials = 'Giriş bilgileri doğrulanamadı.';
  static const String generic = 'Beklenmeyen bir hata oluştu.';

  /// Message for a failure on the login / apple-login screens.
  static String forLogin(Object error) {
    if (error is AppleCredentialException) {
      return error.message;
    }
    if (error is ApiException) {
      if (error.statusCode == 503) {
        return appleUnavailable;
      }
      if (error.statusCode == 401) {
        return invalidCredentials;
      }
      return error.message;
    }
    return generic;
  }

  /// Message for a failure on the account-link screen.
  static String forLink(Object error) {
    if (error is ApiException) {
      // 400 from /auth/apple/link means an expired / already-used ticket.
      if (error.statusCode == 400) {
        return linkTicketInvalid;
      }
      if (error.statusCode == 401) {
        return invalidCredentials;
      }
      if (error.statusCode == 503) {
        return appleUnavailable;
      }
      return error.message;
    }
    return generic;
  }

  /// Message for a failure on the account (status/unlink) screen.
  static String forAccount(Object error) {
    if (error is ApiException) {
      if (error.statusCode == 400) {
        return invalidCredentials;
      }
      return error.message;
    }
    return generic;
  }
}
