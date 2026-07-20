import '../domain/auth_session.dart';

/// Persists the authenticated [AuthSession] in platform secure storage
/// (iOS Keychain / Android Keystore-backed).
///
/// Tokens are stored only here — never in SharedPreferences, never logged.
/// Writes are performed atomically per key; [save] replaces both tokens and
/// [clear] removes every auth key so no partial session can survive.
abstract class SecureSessionStore {
  Future<AuthSession?> read();
  Future<void> save(AuthSession session);

  /// Overwrites only the rotating token pair, keeping identity metadata.
  Future<void> updateTokens({
    required String accessToken,
    required String refreshToken,
  });

  Future<void> clear();
}

class _UnsupportedSecureSessionStore implements SecureSessionStore {
  const _UnsupportedSecureSessionStore();

  @override
  Future<AuthSession?> read() {
    throw UnsupportedError(
      'SecureSessionStore is not supported on this platform.',
    );
  }

  @override
  Future<void> save(AuthSession session) {
    throw UnsupportedError(
      'SecureSessionStore is not supported on this platform.',
    );
  }

  @override
  Future<void> updateTokens({
    required String accessToken,
    required String refreshToken,
  }) {
    throw UnsupportedError(
      'SecureSessionStore is not supported on this platform.',
    );
  }

  @override
  Future<void> clear() {
    throw UnsupportedError(
      'SecureSessionStore is not supported on this platform.',
    );
  }
}

SecureSessionStore createStore() => const _UnsupportedSecureSessionStore();
