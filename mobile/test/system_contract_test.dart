import 'dart:convert';
import 'dart:io';

import 'package:emsalist_mobile/core/data/system/system_api.dart';
import 'package:flutter_test/flutter_test.dart';

/// Verifies that the endpoints the mobile client depends on exist in the
/// backend OpenAPI snapshot, with the expected GET operations. This is a
/// targeted contract check, not full client codegen.
void main() {
  late Map<String, dynamic> spec;

  setUpAll(() {
    final File file = File('../docs/api/openapi-v1.json');
    expect(
      file.existsSync(),
      isTrue,
      reason: 'OpenAPI snapshot not found at ${file.path}',
    );
    spec = jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
  });

  test('snapshot exposes an OpenAPI paths object', () {
    expect(spec['paths'], isA<Map<String, dynamic>>());
  });

  test('GET ${SystemApi.versionPath} exists', () {
    final Map<String, dynamic> paths = spec['paths'] as Map<String, dynamic>;
    expect(paths.containsKey(SystemApi.versionPath), isTrue);
    final Map<String, dynamic> ops =
        paths[SystemApi.versionPath] as Map<String, dynamic>;
    expect(ops.containsKey('get'), isTrue);
  });

  test('GET ${SystemApi.healthPath} exists', () {
    final Map<String, dynamic> paths = spec['paths'] as Map<String, dynamic>;
    expect(paths.containsKey(SystemApi.healthPath), isTrue);
    final Map<String, dynamic> ops =
        paths[SystemApi.healthPath] as Map<String, dynamic>;
    expect(ops.containsKey('get'), isTrue);
  });

  test('version + health operations declare a 200 response', () {
    final Map<String, dynamic> paths = spec['paths'] as Map<String, dynamic>;
    for (final String path in <String>[
      SystemApi.versionPath,
      SystemApi.healthPath,
    ]) {
      final Map<String, dynamic> get =
          (paths[path] as Map<String, dynamic>)['get'] as Map<String, dynamic>;
      final Map<String, dynamic> responses =
          get['responses'] as Map<String, dynamic>;
      expect(
        responses.containsKey('200'),
        isTrue,
        reason: '$path GET should declare a 200 response',
      );
    }
  });
}
