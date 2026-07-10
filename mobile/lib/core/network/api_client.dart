/// Transport-agnostic API client used by repositories.
///
/// Feature widgets and UI never depend on Dio directly; they go through a
/// repository that depends on this abstraction.
abstract class ApiClient {
  /// Performs a GET request and returns the decoded JSON body.
  ///
  /// Throws an [ApiException] (see `api_exception.dart`) on any failure.
  Future<T> getJson<T>(
    String path, {
    Map<String, dynamic>? queryParameters,
    Object? cancelToken,
  });

  /// Performs a POST request with an optional JSON [body] and returns the
  /// decoded JSON body.
  ///
  /// Throws an [ApiException] (see `api_exception.dart`) on any failure.
  Future<T> postJson<T>(
    String path, {
    Object? body,
    Map<String, dynamic>? queryParameters,
    Object? cancelToken,
  });
}
