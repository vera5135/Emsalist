// ignore_for_file: avoid_web_libraries_in_flutter, deprecated_member_use

import 'dart:html' as html;

import '../domain/auth_session.dart';
import 'secure_session_store_base.dart';

export 'secure_session_store_base.dart';

class WebSecureSessionStore implements SecureSessionStore {
  const WebSecureSessionStore();

  static const String _kAccessToken = 'emsalist.auth.access_token';
  static const String _kRefreshToken = 'emsalist.auth.refresh_token';
  static const String _kUserId = 'emsalist.auth.user_id';
  static const String _kTenant = 'emsalist.auth.tenant';
  static const String _kRole = 'emsalist.auth.role';

  html.Storage get _storage => html.window.localStorage;

  @override
  Future<AuthSession?> read() async {
    final String? access = _storage[_kAccessToken];
    final String? refresh = _storage[_kRefreshToken];
    if (access == null ||
        access.isEmpty ||
        refresh == null ||
        refresh.isEmpty) {
      return null;
    }
    return AuthSession(
      accessToken: access,
      refreshToken: refresh,
      userId: _storage[_kUserId],
      tenant: _storage[_kTenant],
      role: _storage[_kRole],
    );
  }

  @override
  Future<void> save(AuthSession session) async {
    _storage[_kAccessToken] = session.accessToken;
    _storage[_kRefreshToken] = session.refreshToken;
    _writeOrDelete(_kUserId, session.userId);
    _writeOrDelete(_kTenant, session.tenant);
    _writeOrDelete(_kRole, session.role);
  }

  @override
  Future<void> updateTokens({
    required String accessToken,
    required String refreshToken,
  }) async {
    _storage[_kAccessToken] = accessToken;
    _storage[_kRefreshToken] = refreshToken;
  }

  @override
  Future<void> clear() async {
    _storage.remove(_kAccessToken);
    _storage.remove(_kRefreshToken);
    _storage.remove(_kUserId);
    _storage.remove(_kTenant);
    _storage.remove(_kRole);
  }

  void _writeOrDelete(String key, String? value) {
    if (value == null || value.isEmpty) {
      _storage.remove(key);
    } else {
      _storage[key] = value;
    }
  }
}

SecureSessionStore createStore() => const WebSecureSessionStore();
