import 'package:emsalist_mobile/features/auth/data/session_manager.dart';
import 'package:emsalist_mobile/features/auth/data/token_refresher.dart';
import 'package:emsalist_mobile/features/auth/domain/auth_session.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/auth_test_support.dart';

/// Configurable fake refresher.
class _FakeRefresher implements TokenRefresher {
  _FakeRefresher({this.result, this.delay = Duration.zero});

  RefreshedTokens? result;
  Duration delay;
  int calls = 0;
  final List<String> seenRefreshTokens = <String>[];

  @override
  Future<RefreshedTokens?> refresh(String refreshToken) async {
    calls++;
    seenRefreshTokens.add(refreshToken);
    if (delay > Duration.zero) {
      await Future<void>.delayed(delay);
    }
    return result;
  }
}

void main() {
  group('SessionManager', () {
    test('restore loads persisted session into memory', () async {
      final FakeSecureSessionStore store = FakeSecureSessionStore(kTestSession);
      final SessionManager manager = SessionManager(
        store: store,
        refresher: _FakeRefresher(),
      );

      final AuthSession? restored = await manager.restore();

      expect(restored, isNotNull);
      expect(manager.hasSession, isTrue);
      expect(manager.accessToken, 'test-access');
    });

    test('establish saves the session to secure storage', () async {
      final FakeSecureSessionStore store = FakeSecureSessionStore();
      final SessionManager manager = SessionManager(
        store: store,
        refresher: _FakeRefresher(),
      );

      await manager.establish(kTestSession);

      expect(store.current, isNotNull);
      expect(store.saveCount, 1);
      expect(manager.currentSession?.refreshToken, 'test-refresh');
    });

    test('refresh rotates tokens and atomically replaces the pair', () async {
      final FakeSecureSessionStore store = FakeSecureSessionStore(kTestSession);
      final _FakeRefresher refresher = _FakeRefresher(
        result: const RefreshedTokens(
          accessToken: 'new-access',
          refreshToken: 'new-refresh',
        ),
      );
      final SessionManager manager = SessionManager(
        store: store,
        refresher: refresher,
      );
      await manager.restore();

      final String? token = await manager.refresh();

      expect(token, 'new-access');
      expect(manager.accessToken, 'new-access');
      expect(manager.currentSession?.refreshToken, 'new-refresh');
      // Old refresh token was the one presented for rotation.
      expect(refresher.seenRefreshTokens, <String>['test-refresh']);
      // Atomic token replacement path used.
      expect(store.updateTokensCount, 1);
      expect(store.current?.refreshToken, 'new-refresh');
    });

    test('concurrent refresh calls are collapsed (single-flight)', () async {
      final FakeSecureSessionStore store = FakeSecureSessionStore(kTestSession);
      final _FakeRefresher refresher = _FakeRefresher(
        result: const RefreshedTokens(
          accessToken: 'new-access',
          refreshToken: 'new-refresh',
        ),
        delay: const Duration(milliseconds: 50),
      );
      final SessionManager manager = SessionManager(
        store: store,
        refresher: refresher,
      );
      await manager.restore();

      final List<String?> results = await Future.wait<String?>(
        <Future<String?>>[
          manager.refresh(),
          manager.refresh(),
          manager.refresh(),
        ],
      );

      expect(results, <String?>['new-access', 'new-access', 'new-access']);
      // Only one network rotation despite three concurrent callers.
      expect(refresher.calls, 1);
    });

    test('failed refresh clears the session entirely', () async {
      final FakeSecureSessionStore store = FakeSecureSessionStore(kTestSession);
      bool cleared = false;
      final SessionManager manager = SessionManager(
        store: store,
        refresher: _FakeRefresher(result: null),
        onSessionCleared: () => cleared = true,
      );
      await manager.restore();

      final String? token = await manager.refresh();

      expect(token, isNull);
      expect(manager.hasSession, isFalse);
      expect(store.current, isNull);
      expect(store.clearCount, greaterThanOrEqualTo(1));
      expect(cleared, isTrue);
    });

    test(
      'refresh with a stale previous access token reuses fresh token',
      () async {
        final FakeSecureSessionStore store = FakeSecureSessionStore(
          kTestSession,
        );
        final _FakeRefresher refresher = _FakeRefresher(
          result: const RefreshedTokens(
            accessToken: 'rotated',
            refreshToken: 'rotated-refresh',
          ),
        );
        final SessionManager manager = SessionManager(
          store: store,
          refresher: refresher,
        );
        await manager.restore();

        // First refresh rotates to 'rotated'.
        await manager.refresh(previousAccessToken: 'test-access');
        // A late caller still holding the original token must not rotate again.
        final String? token = await manager.refresh(
          previousAccessToken: 'test-access',
        );

        expect(token, 'rotated');
        expect(refresher.calls, 1);
      },
    );

    test('clear removes session and is idempotent', () async {
      final FakeSecureSessionStore store = FakeSecureSessionStore(kTestSession);
      final SessionManager manager = SessionManager(
        store: store,
        refresher: _FakeRefresher(),
      );
      await manager.restore();

      await manager.clear();
      await manager.clear();

      expect(manager.hasSession, isFalse);
      expect(store.current, isNull);
    });
  });
}
