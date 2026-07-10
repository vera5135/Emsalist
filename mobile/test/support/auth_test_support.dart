import 'package:emsalist_mobile/app/app.dart';
import 'package:emsalist_mobile/features/auth/application/auth_providers.dart';
import 'package:emsalist_mobile/features/auth/data/apple_credential_provider.dart';
import 'package:emsalist_mobile/features/auth/data/secure_session_store.dart';
import 'package:emsalist_mobile/features/auth/domain/auth_session.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// In-memory [SecureSessionStore] for tests — never touches platform channels.
class FakeSecureSessionStore implements SecureSessionStore {
  FakeSecureSessionStore([AuthSession? initial]) : _session = initial;

  AuthSession? _session;

  int saveCount = 0;
  int clearCount = 0;
  int updateTokensCount = 0;

  AuthSession? get current => _session;

  @override
  Future<AuthSession?> read() async => _session;

  @override
  Future<void> save(AuthSession session) async {
    _session = session;
    saveCount++;
  }

  @override
  Future<void> updateTokens({
    required String accessToken,
    required String refreshToken,
  }) async {
    final AuthSession? existing = _session;
    _session =
        (existing ?? const AuthSession(accessToken: '', refreshToken: ''))
            .copyWith(accessToken: accessToken, refreshToken: refreshToken);
    updateTokensCount++;
  }

  @override
  Future<void> clear() async {
    _session = null;
    clearCount++;
  }
}

/// A ready-made authenticated session for tests.
const AuthSession kTestSession = AuthSession(
  accessToken: 'test-access',
  refreshToken: 'test-refresh',
  userId: 'u-1',
  tenant: 't-1',
  role: 'lawyer',
);

/// Overrides that make the app boot straight into the authenticated shell,
/// with a fake secure store and an unavailable Apple provider (no channels).
List<Override> authenticatedOverrides({
  AuthSession session = kTestSession,
  List<Override> extra = const <Override>[],
}) {
  return <Override>[
    secureSessionStoreProvider.overrideWithValue(
      FakeSecureSessionStore(session),
    ),
    appleCredentialProvider.overrideWithValue(
      const UnavailableAppleCredentialProvider(),
    ),
    ...extra,
  ];
}

/// The full app wrapped in a [ProviderScope] with an authenticated session.
Widget authenticatedApp({List<Override> extra = const <Override>[]}) {
  return ProviderScope(
    overrides: authenticatedOverrides(extra: extra),
    child: const EmsalistApp(),
  );
}
