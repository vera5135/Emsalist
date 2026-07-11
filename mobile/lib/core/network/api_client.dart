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

  /// Performs a DELETE request and returns the decoded JSON body (or an empty
  /// map for 204 responses).
  Future<T> deleteJson<T>(String path, {Object? cancelToken});

  /// Uploads raw [bytes] as a multipart/form-data file field named `file`,
  /// with optional string [fields], returning the decoded JSON body.
  Future<T> uploadBytes<T>(
    String path, {
    required List<int> bytes,
    required String filename,
    String? mimeType,
    Map<String, String> fields = const <String, String>{},
    Object? cancelToken,
  });
}
