import 'package:emsalist_mobile/features/auth/application/auth_controller.dart';
import 'package:emsalist_mobile/features/auth/application/auth_state.dart';
import 'package:emsalist_mobile/features/auth/data/auth_api.dart';
import 'package:emsalist_mobile/features/auth/data/auth_repository.dart';
import 'package:emsalist_mobile/features/auth/data/session_manager.dart';
import 'package:emsalist_mobile/features/auth/data/token_refresher.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/auth_test_support.dart';
import 'support/fake_api_client.dart';
import 'support/fake_apple_credential_provider.dart';

class _NoopRefresher implements TokenRefresher {
  @override
  Future<RefreshedTokens?> refresh(String refreshToken) async => null;
}

AuthController _controller({
  required FakeSecureSessionStore store,
  required FakeApiClient client,
  FakeAppleCredentialProvider? apple,
}) {
  final SessionManager manager = SessionManager(
    store: store,
    refresher: _NoopRefresher(),
  );
  final AuthRepository repo = AuthRepository(
    api: AuthApi(client),
    appleCredentialProvider: apple ?? FakeAppleCredentialProvider(),
  );
  return AuthController(sessionManager: manager, repository: repo);
}

void main() {
  test('starts in unknown status', () {
    final AuthController controller = _controller(
      store: FakeSecureSessionStore(),
      client: FakeApiClient(),
    );
    expect(controller.state.status, AuthStatus.unknown);
  });

  test('bootstrap with persisted session → authenticated', () async {
    final AuthController controller = _controller(
      store: FakeSecureSessionStore(kTestSession),
      client: FakeApiClient(),
      apple: FakeAppleCredentialProvider(available: true),
    );

    await controller.bootstrap();

    expect(controller.state.status, AuthStatus.authenticated);
    expect(controller.state.session?.accessToken, 'test-access');
    expect(controller.state.appleAvailable, isTrue);
  });

  test('bootstrap with no session → unauthenticated', () async {
    final AuthController controller = _controller(
      store: FakeSecureSessionStore(),
      client: FakeApiClient(),
      apple: FakeAppleCredentialProvider(available: false),
    );

    await controller.bootstrap();

    expect(controller.state.status, AuthStatus.unauthenticated);
    expect(controller.state.appleAvailable, isFalse);
  });

  test('password login establishes an authenticated session', () async {
    final FakeApiClient client = FakeApiClient()
      ..whenPost(AuthApi.loginPath, <String, dynamic>{
        'access_token': 'acc',
        'refresh_token': 'ref',
      });
    final FakeSecureSessionStore store = FakeSecureSessionStore();
    final AuthController controller = _controller(store: store, client: client);
    await controller.bootstrap();

    await controller.loginWithPassword(email: 'a@b.com', password: 'secret');

    expect(controller.state.status, AuthStatus.authenticated);
    expect(store.current?.accessToken, 'acc');
  });

  test('logout clears session and returns to unauthenticated', () async {
    final FakeApiClient client = FakeApiClient()
      ..whenPost(AuthApi.logoutPath, <String, dynamic>{'message': 'ok'});
    final FakeSecureSessionStore store = FakeSecureSessionStore(kTestSession);
    final AuthController controller = _controller(store: store, client: client);
    await controller.bootstrap();
    expect(controller.state.status, AuthStatus.authenticated);

    await controller.logout();

    expect(controller.state.status, AuthStatus.unauthenticated);
    expect(controller.state.session, isNull);
    expect(store.current, isNull);
  });

  test('logout clears locally even if backend logout fails', () async {
    final FakeApiClient client = FakeApiClient()
      ..whenPostError(AuthApi.logoutPath, StateError('network'));
    final FakeSecureSessionStore store = FakeSecureSessionStore(kTestSession);
    final AuthController controller = _controller(store: store, client: client);
    await controller.bootstrap();

    await controller.logout();

    expect(controller.state.status, AuthStatus.unauthenticated);
    expect(store.current, isNull);
  });

  test('onSessionCleared flips authenticated → unauthenticated', () async {
    final AuthController controller = _controller(
      store: FakeSecureSessionStore(kTestSession),
      client: FakeApiClient(),
    );
    await controller.bootstrap();
    expect(controller.state.status, AuthStatus.authenticated);

    controller.onSessionCleared();

    expect(controller.state.status, AuthStatus.unauthenticated);
    expect(controller.state.session, isNull);
  });
}
