import 'package:emsalist_mobile/features/auth/data/secure_session_store.dart';
import 'package:emsalist_mobile/features/auth/domain/auth_session.dart';
import 'package:flutter/services.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';

/// In-memory backing for the flutter_secure_storage method channel so the
/// store can be exercised without a platform.
class _InMemorySecureStorageChannel {
  final Map<String, String> _data = <String, String>{};

  void install() {
    const MethodChannel channel = MethodChannel(
      'plugins.it_nomads.com/flutter_secure_storage',
    );
    TestWidgetsFlutterBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, _handle);
  }

  Future<Object?> _handle(MethodCall call) async {
    final Map<Object?, Object?> args =
        (call.arguments as Map<Object?, Object?>?) ?? <Object?, Object?>{};
    final String? key = args['key'] as String?;
    switch (call.method) {
      case 'write':
        _data[key!] = args['value'] as String;
        return null;
      case 'read':
        return _data[key];
      case 'delete':
        _data.remove(key);
        return null;
      case 'readAll':
        return Map<String, String>.from(_data);
      case 'deleteAll':
        _data.clear();
        return null;
      case 'containsKey':
        return _data.containsKey(key);
      default:
        return null;
    }
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late FlutterSecureSessionStore store;

  setUp(() {
    _InMemorySecureStorageChannel().install();
    store = const FlutterSecureSessionStore(storage: FlutterSecureStorage());
  });

  test('read returns null when nothing is stored', () async {
    expect(await store.read(), isNull);
  });

  test('save then read round-trips the session', () async {
    await store.save(
      const AuthSession(
        accessToken: 'acc',
        refreshToken: 'ref',
        userId: 'u1',
        tenant: 't1',
        role: 'lawyer',
      ),
    );

    final AuthSession? loaded = await store.read();
    expect(loaded, isNotNull);
    expect(loaded!.accessToken, 'acc');
    expect(loaded.refreshToken, 'ref');
    expect(loaded.userId, 'u1');
    expect(loaded.tenant, 't1');
    expect(loaded.role, 'lawyer');
  });

  test('updateTokens replaces only the token pair', () async {
    await store.save(
      const AuthSession(accessToken: 'acc', refreshToken: 'ref', userId: 'u1'),
    );

    await store.updateTokens(accessToken: 'acc2', refreshToken: 'ref2');

    final AuthSession? loaded = await store.read();
    expect(loaded!.accessToken, 'acc2');
    expect(loaded.refreshToken, 'ref2');
    expect(loaded.userId, 'u1');
  });

  test('clear removes all auth keys', () async {
    await store.save(
      const AuthSession(accessToken: 'acc', refreshToken: 'ref', userId: 'u1'),
    );

    await store.clear();

    expect(await store.read(), isNull);
  });

  test('read returns null when only a partial token pair exists', () async {
    // Only an access token written directly — refresh missing.
    const FlutterSecureStorage raw = FlutterSecureStorage();
    await raw.write(key: 'emsalist.auth.access_token', value: 'acc');

    expect(await store.read(), isNull);
  });

  tearDown(() {
    TestWidgetsFlutterBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
          const MethodChannel('plugins.it_nomads.com/flutter_secure_storage'),
          null,
        );
  });
}
