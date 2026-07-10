import 'dart:async';

import '../domain/auth_session.dart';
import 'secure_session_store.dart';
import 'token_refresher.dart';

/// Owns the live [AuthSession] and mediates secure-storage persistence and
/// refresh-token rotation.
///
/// Guarantees:
/// - Access/refresh tokens live only in memory and [SecureSessionStore];
///   they are never logged.
/// - Rotation writes the new refresh token atomically over the old one
///   (single [updateTokens] call) before returning it.
/// - Concurrent refresh requests are collapsed into a single in-flight
///   rotation (single-flight) so parallel 401s cannot each burn the refresh
///   token and trip backend reuse-detection.
/// - On any refresh failure the entire session is cleared.
class SessionManager {
  SessionManager({
    required SecureSessionStore store,
    required TokenRefresher refresher,
    void Function()? onSessionCleared,
  }) : _store = store,
       _refresher = refresher,
       _onSessionCleared = onSessionCleared;

  final SecureSessionStore _store;
  final TokenRefresher _refresher;
  final void Function()? _onSessionCleared;

  AuthSession? _session;
  Future<String?>? _inFlightRefresh;

  AuthSession? get currentSession => _session;
  bool get hasSession => _session != null;
  String? get accessToken => _session?.accessToken;

  /// Loads any persisted session into memory. Returns it (or null).
  Future<AuthSession?> restore() async {
    final AuthSession? persisted = await _store.read();
    _session = persisted;
    return persisted;
  }

  /// Establishes a brand-new session (after login/link) and persists it.
  Future<void> establish(AuthSession session) async {
    _session = session;
    await _store.save(session);
  }

  /// Clears the session from memory and secure storage. Idempotent.
  Future<void> clear() async {
    _session = null;
    await _store.clear();
    _onSessionCleared?.call();
  }

  /// Rotates the refresh token, returning the new access token, or null when
  /// the session is no longer valid (in which case it has been cleared).
  ///
  /// [previousAccessToken] lets a caller signal which access token failed; if
  /// the in-memory access token has already been rotated by a concurrent
  /// refresh, this call reuses the fresh token instead of rotating again.
  Future<String?> refresh({String? previousAccessToken}) {
    final AuthSession? current = _session;
    if (current == null) {
      return Future<String?>.value(null);
    }

    if (previousAccessToken != null &&
        previousAccessToken != current.accessToken) {
      // Another refresh already produced a newer access token.
      return Future<String?>.value(current.accessToken);
    }

    return _inFlightRefresh ??= _performRefresh(current).whenComplete(() {
      _inFlightRefresh = null;
    });
  }

  Future<String?> _performRefresh(AuthSession current) async {
    final RefreshedTokens? rotated = await _refresher.refresh(
      current.refreshToken,
    );
    if (rotated == null) {
      await clear();
      return null;
    }

    final AuthSession updated = current.copyWith(
      accessToken: rotated.accessToken,
      refreshToken: rotated.refreshToken,
    );
    _session = updated;
    // Atomic replacement of the rotating token pair.
    await _store.updateTokens(
      accessToken: rotated.accessToken,
      refreshToken: rotated.refreshToken,
    );
    return rotated.accessToken;
  }
}
