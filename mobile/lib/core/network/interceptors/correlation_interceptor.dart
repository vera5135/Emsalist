import 'dart:math';

import 'package:dio/dio.dart';

/// Adds an `X-Correlation-ID` header to every request when one is not already
/// present, so client requests can be traced end-to-end with the backend.
class CorrelationInterceptor extends Interceptor {
  CorrelationInterceptor({String Function()? idGenerator})
    : _idGenerator = idGenerator ?? _defaultIdGenerator;

  static const String headerName = 'X-Correlation-ID';

  final String Function() _idGenerator;

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    final bool hasHeader = options.headers.keys.any(
      (String key) => key.toLowerCase() == headerName.toLowerCase(),
    );
    if (!hasHeader) {
      options.headers[headerName] = _idGenerator();
    }
    handler.next(options);
  }

  static String _defaultIdGenerator() {
    final Random random = Random();
    final int now = DateTime.now().microsecondsSinceEpoch;
    final int salt = random.nextInt(0x7fffffff);
    return 'm-${now.toRadixString(16)}-${salt.toRadixString(16)}';
  }
}
