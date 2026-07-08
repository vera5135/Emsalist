import 'dart:async';

import 'package:emsalist_mobile/core/config/api_configuration_exception.dart';
import 'package:emsalist_mobile/core/data/system/system_repository.dart';
import 'package:emsalist_mobile/core/network/api_exception.dart';
import 'package:emsalist_mobile/core/providers/system_status_provider.dart';
import 'package:emsalist_mobile/features/system/system_status_sheet.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

Widget _host(List<Override> overrides) {
  return ProviderScope(
    overrides: overrides,
    child: const MaterialApp(home: Scaffold(body: SystemStatusSheet())),
  );
}

const SystemStatus _healthy = SystemStatus(
  health: BackendHealth.healthy,
  application: 'emsalist',
  version: '0.1.0',
  apiVersion: 'v1',
  commit: 'abc123',
  environment: 'development',
  serviceName: 'emsalist-api',
);

void main() {
  testWidgets('shows loading indicator while pending', (
    WidgetTester tester,
  ) async {
    final Completer<SystemStatus> completer = Completer<SystemStatus>();
    addTearDown(() {
      if (!completer.isCompleted) {
        completer.complete(_healthy);
      }
    });
    await tester.pumpWidget(
      _host(<Override>[
        systemStatusProvider.overrideWith((ref) => completer.future),
      ]),
    );
    await tester.pump();

    expect(find.text('Sistem Durumu'), findsOneWidget);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
  });

  testWidgets('shows backend data on success', (WidgetTester tester) async {
    await tester.pumpWidget(
      _host(<Override>[
        systemStatusProvider.overrideWith((ref) async => _healthy),
      ]),
    );
    await tester.pumpAndSettle();

    expect(find.text('Sağlıklı'), findsOneWidget);
    expect(find.text('0.1.0'), findsOneWidget);
    expect(find.text('v1'), findsOneWidget);
    expect(find.text('abc123'), findsOneWidget);
  });

  testWidgets('shows error with correlation id and retry', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      _host(<Override>[
        systemStatusProvider.overrideWith(
          (ref) async => throw const ApiException(
            kind: ApiErrorKind.server,
            message: 'Sunucu hatası oluştu.',
            statusCode: 500,
            correlationId: 'corr-xyz',
          ),
        ),
      ]),
    );
    await tester.pumpAndSettle();

    expect(find.text('Bağlantı hatası'), findsOneWidget);
    expect(find.textContaining('corr-xyz'), findsOneWidget);
    expect(find.widgetWithText(FilledButton, 'Yeniden Dene'), findsOneWidget);
  });

  testWidgets('shows offline state for network error', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      _host(<Override>[
        systemStatusProvider.overrideWith(
          (ref) async => throw const ApiException(
            kind: ApiErrorKind.network,
            message: 'Bağlantı kurulamadı.',
          ),
        ),
      ]),
    );
    await tester.pumpAndSettle();

    expect(find.text('Çevrimdışı'), findsOneWidget);
    expect(find.widgetWithText(FilledButton, 'Yeniden Dene'), findsOneWidget);
  });

  testWidgets('shows configuration missing state', (WidgetTester tester) async {
    await tester.pumpWidget(
      _host(<Override>[
        systemStatusProvider.overrideWith(
          (ref) async => throw const ApiConfigurationException(
            'API_BASE_URL missing',
            environment: 'staging',
          ),
        ),
      ]),
    );
    await tester.pumpAndSettle();

    expect(find.text('Yapılandırma eksik'), findsOneWidget);
    expect(find.widgetWithText(FilledButton, 'Yeniden Dene'), findsOneWidget);
  });

  testWidgets('retry re-invokes the provider', (WidgetTester tester) async {
    int calls = 0;
    await tester.pumpWidget(
      _host(<Override>[
        systemStatusProvider.overrideWith((ref) async {
          calls++;
          if (calls == 1) {
            throw const ApiException(
              kind: ApiErrorKind.network,
              message: 'Bağlantı kurulamadı.',
            );
          }
          return _healthy;
        }),
      ]),
    );
    await tester.pumpAndSettle();
    expect(find.text('Çevrimdışı'), findsOneWidget);

    await tester.tap(find.widgetWithText(FilledButton, 'Yeniden Dene'));
    await tester.pumpAndSettle();

    expect(calls, greaterThanOrEqualTo(2));
    expect(find.text('Sağlıklı'), findsOneWidget);
  });

  testWidgets('no overflow at small viewport with high text scale', (
    WidgetTester tester,
  ) async {
    tester.view.physicalSize = const Size(375, 812) * 3.0;
    tester.view.devicePixelRatio = 3.0;
    tester.platformDispatcher.textScaleFactorTestValue = 1.5;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);

    await tester.pumpWidget(
      _host(<Override>[
        systemStatusProvider.overrideWith((ref) async => _healthy),
      ]),
    );
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
  });
}
