import 'package:emsalist_mobile/core/network/api_client.dart';
import 'package:emsalist_mobile/core/network/api_exception.dart';

/// A programmable in-memory [ApiClient] for auth flow tests.
///
/// Queue a JSON map or an error per path+method. Records calls for assertions.
class FakeApiClient implements ApiClient {
  FakeApiClient();

  final Map<String, Object> _getResponses = <String, Object>{};
  final Map<String, Object> _postResponses = <String, Object>{};
  final Map<String, Object> _getErrors = <String, Object>{};
  final Map<String, Object> _postErrors = <String, Object>{};

  final List<String> getPaths = <String>[];
  final List<String> postPaths = <String>[];
  final List<Object?> postBodies = <Object?>[];

  void whenGet(String path, Map<String, dynamic> response) {
    _getResponses[path] = response;
  }

  void whenGetError(String path, Object error) {
    _getErrors[path] = error;
  }

  void whenPost(String path, Map<String, dynamic> response) {
    _postResponses[path] = response;
  }

  void whenPostError(String path, Object error) {
    _postErrors[path] = error;
  }

  @override
  Future<T> getJson<T>(
    String path, {
    Map<String, dynamic>? queryParameters,
    Object? cancelToken,
  }) async {
    getPaths.add(path);
    final Object? error = _getErrors[path];
    if (error != null) {
      throw error;
    }
    final Object? value = _getResponses[path];
    if (value is T) {
      return value;
    }
    throw const ApiException(
      kind: ApiErrorKind.unexpected,
      message: 'no fake GET',
    );
  }

  @override
  Future<T> postJson<T>(
    String path, {
    Object? body,
    Map<String, dynamic>? queryParameters,
    Object? cancelToken,
  }) async {
    postPaths.add(path);
    postBodies.add(body);
    final Object? error = _postErrors[path];
    if (error != null) {
      throw error;
    }
    final Object? value = _postResponses[path];
    if (value is T) {
      return value;
    }
    throw const ApiException(
      kind: ApiErrorKind.unexpected,
      message: 'no fake POST',
    );
  }
}
