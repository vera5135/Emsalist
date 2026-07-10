import 'package:emsalist_mobile/features/auth/data/apple_credential_provider.dart';

/// Configurable fake for the Apple native credential seam.
///
/// - [available] controls [isAvailable].
/// - Provide [credential] to succeed, [error] to fail, or set [cancelled] to
///   simulate a user cancel.
/// - Records the raw nonce it was asked to sign so tests can assert binding.
class FakeAppleCredentialProvider implements AppleCredentialProvider {
  FakeAppleCredentialProvider({
    this.available = true,
    this.credential,
    this.error,
    this.cancelled = false,
  });

  bool available;
  AppleCredential? credential;
  Object? error;
  bool cancelled;

  String? lastRawNonce;
  int getCredentialCalls = 0;

  @override
  Future<bool> isAvailable() async => available;

  @override
  Future<AppleCredential> getCredential({required String rawNonce}) async {
    getCredentialCalls++;
    lastRawNonce = rawNonce;
    if (cancelled) {
      throw const AppleCredentialException('cancelled', cancelled: true);
    }
    if (error != null) {
      throw error!;
    }
    return credential ??
        AppleCredential(authorizationCode: 'auth-code', rawNonce: rawNonce);
  }
}
