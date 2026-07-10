import 'package:emsalist_mobile/features/auth/data/auth_api.dart';
import 'package:emsalist_mobile/features/auth/data/auth_repository.dart';
import 'package:emsalist_mobile/core/network/api_exception.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_api_client.dart';
import 'support/fake_apple_credential_provider.dart';

void main() {
  group('AuthRepository — password login', () {
    test('returns a session with both tokens', () async {
      final FakeApiClient client = FakeApiClient()
        ..whenPost(AuthApi.loginPath, <String, dynamic>{
          'access_token': 'acc',
          'refresh_token': 'ref',
          'token_type': 'bearer',
          'user': <String, dynamic>{
            'id': 'u1',
            'tenant': 't1',
            'role': 'lawyer',
          },
        });
      final AuthRepository repo = AuthRepository(
        api: AuthApi(client),
        appleCredentialProvider: FakeAppleCredentialProvider(),
      );

      final session = await repo.loginWithPassword(
        email: 'a@b.com',
        password: 'secret',
      );

      expect(session.accessToken, 'acc');
      expect(session.refreshToken, 'ref');
      expect(session.userId, 'u1');
      expect(client.postPaths, contains(AuthApi.loginPath));
    });

    test('propagates 401 as ApiException', () async {
      final FakeApiClient client = FakeApiClient()
        ..whenPostError(
          AuthApi.loginPath,
          const ApiException(
            kind: ApiErrorKind.server,
            message: 'invalid',
            statusCode: 401,
          ),
        );
      final AuthRepository repo = AuthRepository(
        api: AuthApi(client),
        appleCredentialProvider: FakeAppleCredentialProvider(),
      );

      await expectLater(
        repo.loginWithPassword(email: 'a@b.com', password: 'x'),
        throwsA(isA<ApiException>()),
      );
    });
  });

  group('AuthRepository — Apple sign-in', () {
    test('authenticated result yields a session', () async {
      final FakeApiClient client = FakeApiClient()
        ..whenPost(AuthApi.appleLoginPath, <String, dynamic>{
          'state': 'authenticated',
          'access_token': 'acc',
          'refresh_token': 'ref',
          'user': <String, dynamic>{
            'id': 'u1',
            'tenant': 't1',
            'role': 'lawyer',
          },
        });
      final AuthRepository repo = AuthRepository(
        api: AuthApi(client),
        appleCredentialProvider: FakeAppleCredentialProvider(),
      );

      final result = await repo.signInWithApple();

      expect(result, isA<AppleAuthenticated>());
      expect((result as AppleAuthenticated).session.accessToken, 'acc');
    });

    test('link_required result yields the opaque ticket', () async {
      final FakeApiClient client = FakeApiClient()
        ..whenPost(AuthApi.appleLoginPath, <String, dynamic>{
          'state': 'link_required',
          'link_ticket': 'ticket-xyz',
          'link_expires_in': 300,
        });
      final AuthRepository repo = AuthRepository(
        api: AuthApi(client),
        appleCredentialProvider: FakeAppleCredentialProvider(),
      );

      final result = await repo.signInWithApple();

      expect(result, isA<AppleLinkRequired>());
      expect((result as AppleLinkRequired).linkTicket, 'ticket-xyz');
    });

    test('user cancel yields cancelled result and no backend call', () async {
      final FakeApiClient client = FakeApiClient();
      final AuthRepository repo = AuthRepository(
        api: AuthApi(client),
        appleCredentialProvider: FakeAppleCredentialProvider(cancelled: true),
      );

      final result = await repo.signInWithApple();

      expect(result, isA<AppleSignInCancelled>());
      expect(client.postPaths, isEmpty);
    });

    test('binds raw nonce SHA-256 handoff (credential sees raw nonce)',
        () async {
      final FakeAppleCredentialProvider apple = FakeAppleCredentialProvider();
      final FakeApiClient client = FakeApiClient()
        ..whenPost(AuthApi.appleLoginPath, <String, dynamic>{
          'state': 'authenticated',
          'access_token': 'acc',
          'refresh_token': 'ref',
        });
      final AuthRepository repo = AuthRepository(
        api: AuthApi(client),
        appleCredentialProvider: apple,
      );

      await repo.signInWithApple();

      expect(apple.lastRawNonce, isNotNull);
      expect(apple.lastRawNonce!.length, greaterThanOrEqualTo(16));
      // The raw nonce is forwarded to the backend for binding verification.
      final Object? body = client.postBodies.first;
      expect(body, isA<Map<String, dynamic>>());
      expect((body! as Map<String, dynamic>)['raw_nonce'], apple.lastRawNonce);
    });
  });

  group('AuthRepository — account linking', () {
    test('link success returns a session', () async {
      final FakeApiClient client = FakeApiClient()
        ..whenPost(AuthApi.appleLinkPath, <String, dynamic>{
          'access_token': 'acc',
          'refresh_token': 'ref',
          'user': <String, dynamic>{'id': 'u1', 'tenant': 't1', 'role': 'lawyer'},
        });
      final AuthRepository repo = AuthRepository(
        api: AuthApi(client),
        appleCredentialProvider: FakeAppleCredentialProvider(),
      );

      final session = await repo.linkApple(
        linkTicket: 'ticket',
        email: 'a@b.com',
        password: 'secret',
      );

      expect(session.accessToken, 'acc');
      expect(client.postPaths, contains(AuthApi.appleLinkPath));
    });

    test('expired / used ticket surfaces as 400 ApiException', () async {
      final FakeApiClient client = FakeApiClient()
        ..whenPostError(
          AuthApi.appleLinkPath,
          const ApiException(
            kind: ApiErrorKind.server,
            message: 'Link ticket expired',
            statusCode: 400,
          ),
        );
      final AuthRepository repo = AuthRepository(
        api: AuthApi(client),
        appleCredentialProvider: FakeAppleCredentialProvider(),
      );

      await expectLater(
        repo.linkApple(linkTicket: 't', email: 'a@b.com', password: 'x'),
        throwsA(
          isA<ApiException>().having(
            (ApiException e) => e.statusCode,
            'statusCode',
            400,
          ),
        ),
      );
    });
  });

  group('AuthRepository — status & unlink', () {
    test('appleLinkStatus reflects linked flag', () async {
      final FakeApiClient client = FakeApiClient()
        ..whenGet(AuthApi.appleStatusPath, <String, dynamic>{
          'linked': true,
          'provider': 'apple',
        });
      final AuthRepository repo = AuthRepository(
        api: AuthApi(client),
        appleCredentialProvider: FakeAppleCredentialProvider(),
      );

      expect(await repo.appleLinkStatus(), isTrue);
    });

    test('unlink posts current password', () async {
      final FakeApiClient client = FakeApiClient()
        ..whenPost(AuthApi.appleUnlinkPath, <String, dynamic>{
          'message': 'ok',
        });
      final AuthRepository repo = AuthRepository(
        api: AuthApi(client),
        appleCredentialProvider: FakeAppleCredentialProvider(),
      );

      await repo.unlinkApple(currentPassword: 'secret');

      expect(client.postPaths, contains(AuthApi.appleUnlinkPath));
      final Object? body = client.postBodies.first;
      expect((body! as Map<String, dynamic>)['current_password'], 'secret');
    });
  });

  group('AuthRepository — Apple availability', () {
    test('reports provider availability', () async {
      final repoAvailable = AuthRepository(
        api: AuthApi(FakeApiClient()),
        appleCredentialProvider: FakeAppleCredentialProvider(available: true),
      );
      final repoUnavailable = AuthRepository(
        api: AuthApi(FakeApiClient()),
        appleCredentialProvider: FakeAppleCredentialProvider(available: false),
      );

      expect(await repoAvailable.isAppleAvailable(), isTrue);
      expect(await repoUnavailable.isAppleAvailable(), isFalse);
    });
  });
}
