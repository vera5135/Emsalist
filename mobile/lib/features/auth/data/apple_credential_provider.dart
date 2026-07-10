import 'dart:convert';
import 'dart:math';

import 'package:crypto/crypto.dart';

/// An Apple authorization credential obtained from the native Sign in with
/// Apple flow, ready to exchange with the backend.
class AppleCredential {
  const AppleCredential({
    required this.authorizationCode,
    required this.rawNonce,
  });

  /// The single-use authorization code from Apple.
  final String authorizationCode;

  /// The *raw* nonce generated on-device. The backend expects the ID token's
  /// `nonce` claim to equal SHA-256(rawNonce); it is sent alongside the code so
  /// the backend can verify binding. The raw value is never logged.
  final String rawNonce;
}

/// Raised when an Apple credential cannot be obtained on-device.
///
/// [cancelled] distinguishes an intentional user cancel (no error UI) from a
/// genuine failure or an unavailable capability.
class AppleCredentialException implements Exception {
  const AppleCredentialException(this.message, {this.cancelled = false});

  final String message;
  final bool cancelled;

  @override
  String toString() => 'AppleCredentialException(cancelled: $cancelled)';
}

/// Abstraction over the native "Sign in with Apple" credential acquisition.
///
/// This seam keeps the platform SDK out of the app/business layer so the flow
/// is fully testable with a fake, and so the concrete native implementation
/// can be added later without touching callers.
abstract class AppleCredentialProvider {
  /// Whether the native capability is available on this device/build.
  Future<bool> isAvailable();

  /// Runs the native flow and returns a credential.
  ///
  /// [rawNonce] MUST be the raw nonce whose SHA-256 was passed to Apple as the
  /// `nonce` request parameter, so the returned ID token binds to this device.
  /// Throws [AppleCredentialException] on cancel/failure.
  Future<AppleCredential> getCredential({required String rawNonce});
}

/// Generates cryptographically-strong nonces for the Apple flow.
class AppleNonce {
  const AppleNonce._();

  static const String _charset =
      'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._';

  /// Returns a random raw nonce of [length] characters (default 32).
  static String generateRaw([int length = 32, Random? random]) {
    final Random rng = random ?? Random.secure();
    final StringBuffer buffer = StringBuffer();
    for (int i = 0; i < length; i++) {
      buffer.write(_charset[rng.nextInt(_charset.length)]);
    }
    return buffer.toString();
  }

  /// SHA-256 hex digest of [rawNonce] — the value handed to Apple as `nonce`.
  static String sha256Hex(String rawNonce) {
    return sha256.convert(utf8.encode(rawNonce)).toString();
  }
}

/// Default provider used when no native implementation is wired in.
///
/// P2.2B2B ships the backend-facing flow and secure session; the concrete
/// native Sign in with Apple binding (and its iOS capability) is documented in
/// `docs/p2/P2_MOBILE_APPLE_NATIVE.md` and added when real Apple config exists.
/// Until then this reports unavailable so the UI hides / disables the Apple
/// button gracefully instead of pretending to sign in.
class UnavailableAppleCredentialProvider implements AppleCredentialProvider {
  const UnavailableAppleCredentialProvider();

  @override
  Future<bool> isAvailable() async => false;

  @override
  Future<AppleCredential> getCredential({required String rawNonce}) async {
    throw const AppleCredentialException(
      'Apple ile giriş bu cihazda kullanılamıyor.',
    );
  }
}
