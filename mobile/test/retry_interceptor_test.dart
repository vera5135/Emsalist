import 'dart:async';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:emsalist_mobile/core/network/interceptors/retry_interceptor.dart';
import 'package:flutter_test/flutter_test.dart';

/// A fake adapter that returns queued outcomes in order, recording calls.
class _FakeAdapter implements HttpClientAdapter {
  _FakeAdapter(this._outcomes);

  final List<_Outcome> _outcomes;
  int calls = 0;

  @override
  void close({bool force = false}) {}

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    final _Outcome outcome = _outcomes[calls.clamp(0, _outcomes.length - 1)];
    calls++;
    if (outcome.statusCode != null) {
      return ResponseBody.fromString(
        '{}',
        outcome.statusCode!,
        headers: {
          Headers.contentTypeHeader: <String>[Headers.jsonContentType],
        },
      );
    }
    throw DioException(
      requestOptions: options,
      type: outcome.errorType ?? DioExceptionType.connectionError,
    );
  }
}

class _Outcome {
  const _Outcome.status(this.statusCode) : errorType = null;
  const _Outcome.error(this.errorType) : statusCode = null;

  final int? statusCode;
  final DioExceptionType? errorType;
}

Dio _dioWith(List<_Outcome> outcomes) {
  final Dio dio = Dio(BaseOptions(baseUrl: 'http://localhost:8000'));
  dio.httpClientAdapter = _FakeAdapter(outcomes);
  dio.interceptors.add(
    RetryInterceptor(dio: dio, delay: (Duration _) async {}),
  );
  return dio;
}

void main() {
  test('retries GET on 503 then succeeds', () async {
    final Dio dio = _dioWith(<_Outcome>[
      const _Outcome.status(503),
      const _Outcome.status(200),
    ]);
    final Response<dynamic> res = await dio.get<dynamic>('/health');
    expect(res.statusCode, 200);
    expect((dio.httpClientAdapter as _FakeAdapter).calls, 2);
  });

  test('stops after max 2 retries (3 attempts total)', () async {
    final Dio dio = _dioWith(<_Outcome>[
      const _Outcome.status(503),
      const _Outcome.status(503),
      const _Outcome.status(503),
      const _Outcome.status(503),
    ]);
    await expectLater(
      dio.get<dynamic>('/health'),
      throwsA(isA<DioException>()),
    );
    expect((dio.httpClientAdapter as _FakeAdapter).calls, 3);
  });

  test('does not retry POST', () async {
    final Dio dio = _dioWith(<_Outcome>[
      const _Outcome.status(503),
      const _Outcome.status(200),
    ]);
    await expectLater(
      dio.post<dynamic>('/anything'),
      throwsA(isA<DioException>()),
    );
    expect((dio.httpClientAdapter as _FakeAdapter).calls, 1);
  });

  test('does not retry non-eligible status (400)', () async {
    final Dio dio = _dioWith(<_Outcome>[
      const _Outcome.status(400),
      const _Outcome.status(200),
    ]);
    await expectLater(
      dio.get<dynamic>('/health'),
      throwsA(isA<DioException>()),
    );
    expect((dio.httpClientAdapter as _FakeAdapter).calls, 1);
  });

  test('retries GET on connection error', () async {
    final Dio dio = _dioWith(<_Outcome>[
      const _Outcome.error(DioExceptionType.connectionError),
      const _Outcome.status(200),
    ]);
    final Response<dynamic> res = await dio.get<dynamic>('/health');
    expect(res.statusCode, 200);
    expect((dio.httpClientAdapter as _FakeAdapter).calls, 2);
  });
}
