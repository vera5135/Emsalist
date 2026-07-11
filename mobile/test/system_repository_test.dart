import 'package:emsalist_mobile/core/data/system/system_api.dart';
import 'package:emsalist_mobile/core/data/system/system_repository.dart';
import 'package:emsalist_mobile/core/network/api_client.dart';
import 'package:emsalist_mobile/core/network/api_exception.dart';
import 'package:flutter_test/flutter_test.dart';

/// Handwritten fake: returns queued responses per path or throws.
class _FakeApiClient implements ApiClient {
  _FakeApiClient({this.responses = const <String, Object>{}, this.error});

  final Map<String, Object> responses;
  final Object? error;
  final List<String> requestedPaths = <String>[];

  @override
  Future<T> getJson<T>(
    String path, {
    Map<String, dynamic>? queryParameters,
    Object? cancelToken,
  }) async {
    requestedPaths.add(path);
    if (error != null) {
      throw error!;
    }
    final Object? value = responses[path];
    if (value is T) {
      return value;
    }
    throw StateError('No fake response for $path');
  }

  @override
  Future<T> postJson<T>(
    String path, {
    Object? body,
    Map<String, dynamic>? queryParameters,
    Object? cancelToken,
  }) async {
    requestedPaths.add(path);
    if (error != null) {
      throw error!;
    }
    final Object? value = responses[path];
    if (value is T) {
      return value;
    }
    throw StateError('No fake response for $path');
  }

  @override
  Future<T> deleteJson<T>(String path, {Object? cancelToken}) async {
    requestedPaths.add(path);
    if (error != null) {
      throw error!;
    }
    return <String, dynamic>{} as T;
  }

  @override
  Future<T> uploadBytes<T>(
    String path, {
    required List<int> bytes,
    required String filename,
    String? mimeType,
    Map<String, String> fields = const <String, String>{},
    Object? cancelToken,
  }) async {
    requestedPaths.add(path);
    if (error != null) {
      throw error!;
    }
    final Object? value = responses[path];
    if (value is T) {
      return value;
    }
    throw StateError('No fake response for $path');
  }
}

void main() {
  final Map<String, Object> healthy = <String, Object>{
    SystemApi.versionPath: <String, dynamic>{
      'application': 'emsalist',
      'version': '0.1.0',
      'api_version': 'v1',
      'commit': 'abc123',
      'environment': 'development',
    },
    SystemApi.healthPath: <String, dynamic>{
      'status': 'healthy',
      'service': 'emsalist-api',
      'checks': <String, dynamic>{},
      'components': <String, dynamic>{},
    },
  };

  test('fetchStatus maps version + health into domain', () async {
    final _FakeApiClient client = _FakeApiClient(responses: healthy);
    final SystemRepository repo = SystemRepository(SystemApi(client));

    final SystemStatus status = await repo.fetchStatus();

    expect(status.health, BackendHealth.healthy);
    expect(status.version, '0.1.0');
    expect(status.apiVersion, 'v1');
    expect(status.commit, 'abc123');
    expect(status.hasCommit, isTrue);
    expect(status.serviceName, 'emsalist-api');
    expect(
      client.requestedPaths,
      containsAll(<String>[SystemApi.versionPath, SystemApi.healthPath]),
    );
  });

  test('degraded health maps to degraded', () async {
    final Map<String, Object> degraded = Map<String, Object>.from(healthy)
      ..[SystemApi.healthPath] = <String, dynamic>{
        'status': 'degraded',
        'service': 'emsalist-api',
      };
    final SystemRepository repo = SystemRepository(
      SystemApi(_FakeApiClient(responses: degraded)),
    );

    final SystemStatus status = await repo.fetchStatus();
    expect(status.health, BackendHealth.degraded);
  });

  test('unknown commit is not shown', () async {
    final Map<String, Object> unknownCommit = Map<String, Object>.from(healthy)
      ..[SystemApi.versionPath] = <String, dynamic>{
        'version': '0.1.0',
        'commit': 'unknown',
      };
    final SystemRepository repo = SystemRepository(
      SystemApi(_FakeApiClient(responses: unknownCommit)),
    );

    final SystemStatus status = await repo.fetchStatus();
    expect(status.hasCommit, isFalse);
  });

  test('propagates ApiException from client (offline/server)', () async {
    const ApiException offline = ApiException(
      kind: ApiErrorKind.network,
      message: 'offline',
    );
    final SystemRepository repo = SystemRepository(
      SystemApi(_FakeApiClient(error: offline)),
    );

    await expectLater(repo.fetchStatus(), throwsA(isA<ApiException>()));
  });
}
