import 'package:emsalist_mobile/app/app.dart';
import 'package:emsalist_mobile/core/network/api_exception.dart';
import 'package:emsalist_mobile/features/auth/application/auth_providers.dart';
import 'package:emsalist_mobile/features/auth/data/auth_api.dart';
import 'package:emsalist_mobile/features/auth/presentation/account_link_screen.dart';
import 'package:emsalist_mobile/features/auth/presentation/login_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'support/auth_test_support.dart';
import 'support/fake_api_client.dart';
import 'support/fake_apple_credential_provider.dart';

Widget _app({
  required FakeApiClient client,
  FakeAppleCredentialProvider? apple,
}) {
  return ProviderScope(
    overrides: <Override>[
      secureSessionStoreProvider.overrideWithValue(FakeSecureSessionStore()),
      appleCredentialProvider.overrideWithValue(
        apple ?? FakeAppleCredentialProvider(available: false),
      ),
      // Route auth traffic through the fake API client for the whole graph.
      authenticatedApiClientProvider.overrideWithValue(client),
    ],
    child: const EmsalistApp(),
  );
}

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
  });

  testWidgets('shows validation errors on empty submit', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(_app(client: FakeApiClient()));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Giriş Yap'));
    await tester.pumpAndSettle();

    expect(find.text('E-posta gerekli'), findsOneWidget);
    expect(find.text('Parola gerekli'), findsOneWidget);
  });

  testWidgets('invalid credentials show a safe error message', (
    WidgetTester tester,
  ) async {
    final FakeApiClient client = FakeApiClient()
      ..whenPostError(
        AuthApi.loginPath,
        const ApiException(
          kind: ApiErrorKind.server,
          message: 'Giriş bilgileri doğrulanamadı.',
          statusCode: 401,
        ),
      );
    await tester.pumpWidget(_app(client: client));
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(TextFormField).first, 'a@b.com');
    await tester.enterText(find.byType(TextFormField).last, 'wrong');
    await tester.tap(find.text('Giriş Yap'));
    await tester.pumpAndSettle();

    expect(find.text('Giriş bilgileri doğrulanamadı.'), findsOneWidget);
    // Still on login.
    expect(find.byType(LoginScreen), findsOneWidget);
  });

  testWidgets('Apple button visible when provider available', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      _app(
        client: FakeApiClient(),
        apple: FakeAppleCredentialProvider(available: true),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Apple ile Devam Et'), findsOneWidget);
  });

  testWidgets('Apple 503 unavailable shows a clear message', (
    WidgetTester tester,
  ) async {
    final FakeApiClient client = FakeApiClient()
      ..whenPostError(
        AuthApi.appleLoginPath,
        const ApiException(
          kind: ApiErrorKind.server,
          message: 'unavailable',
          statusCode: 503,
        ),
      );
    await tester.pumpWidget(
      _app(
        client: client,
        apple: FakeAppleCredentialProvider(available: true),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Apple ile Devam Et'));
    await tester.pumpAndSettle();

    expect(
      find.textContaining('Apple ile giriş şu anda kullanılamıyor'),
      findsOneWidget,
    );
  });

  testWidgets('Apple link_required navigates to the link screen', (
    WidgetTester tester,
  ) async {
    final FakeApiClient client = FakeApiClient()
      ..whenPost(AuthApi.appleLoginPath, <String, dynamic>{
        'state': 'link_required',
        'link_ticket': 'secret-ticket',
        'link_expires_in': 300,
      });
    await tester.pumpWidget(
      _app(
        client: client,
        apple: FakeAppleCredentialProvider(available: true),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Apple ile Devam Et'));
    await tester.pumpAndSettle();

    expect(find.byType(AccountLinkScreen), findsOneWidget);
    // The opaque link ticket is never shown to the user.
    expect(find.textContaining('secret-ticket'), findsNothing);
  });
}
