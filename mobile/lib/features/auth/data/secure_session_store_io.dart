import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../domain/auth_session.dart';
import 'secure_session_store_base.dart';

export 'secure_session_store_base.dart';

class FlutterSecureSessionStore implements SecureSessionStore {
  const FlutterSecureSessionStore({FlutterSecureStorage? storage})
    : _storage = storage ?? _defaultStorage;

  final FlutterSecureStorage _storage;

  static const FlutterSecureStorage _defaultStorage = FlutterSecureStorage(
    aOptions: AndroidOptions(),
    iOptions: IOSOptions(accessibility: KeychainAccessibility.first_unlock),
  );

  static const String _kAccessToken = 'emsalist.auth.access_token';
  static const String _kRefreshToken = 'emsalist.auth.refresh_token';
  static const String _kUserId = 'emsalist.auth.user_id';
  static const String _kTenant = 'emsalist.auth.tenant';
  static const String _kRole = 'emsalist.auth.role';

  @override
  Future<AuthSession?> read() async {
    final String? access = await _storage.read(key: _kAccessToken);
    final String? refresh = await _storage.read(key: _kRefreshToken);
    if (access == null ||
        access.isEmpty ||
        refresh == null ||
        refresh.isEmpty) {
      return null;
    }
    return AuthSession(
      accessToken: access,
      refreshToken: refresh,
      userId: await _storage.read(key: _kUserId),
      tenant: await _storage.read(key: _kTenant),
      role: await _storage.read(key: _kRole),
    );
  }

  @override
  Future<void> save(AuthSession session) async {
    await _storage.write(key: _kAccessToken, value: session.accessToken);
    await _storage.write(key: _kRefreshToken, value: session.refreshToken);
    await _writeOrDelete(_kUserId, session.userId);
    await _writeOrDelete(_kTenant, session.tenant);
    await _writeOrDelete(_kRole, session.role);
  }

  @override
  Future<void> updateTokens({
    required String accessToken,
    required String refreshToken,
  }) async {
    await _storage.write(key: _kAccessToken, value: accessToken);
    await _storage.write(key: _kRefreshToken, value: refreshToken);
  }

  @override
  Future<void> clear() async {
    await _storage.delete(key: _kAccessToken);
    await _storage.delete(key: _kRefreshToken);
    await _storage.delete(key: _kUserId);
    await _storage.delete(key: _kTenant);
    await _storage.delete(key: _kRole);
  }

  Future<void> _writeOrDelete(String key, String? value) async {
    if (value == null || value.isEmpty) {
      await _storage.delete(key: key);
    } else {
      await _storage.write(key: key, value: value);
    }
  }
}

SecureSessionStore createStore() => const FlutterSecureSessionStore();
