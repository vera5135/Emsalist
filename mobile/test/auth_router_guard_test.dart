import 'package:emsalist_mobile/app/app.dart';
import 'package:emsalist_mobile/features/auth/application/auth_providers.dart';
import 'package:emsalist_mobile/features/auth/data/apple_credential_provider.dart';
import 'package:emsalist_mobile/features/auth/presentation/login_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'support/auth_test_support.dart';

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
  });

  testWidgets('unauthenticated user lands on the login screen', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          secureSessionStoreProvider.overrideWithValue(
            FakeSecureSessionStore(),
          ),
          appleCredentialProvider.overrideWithValue(
            const UnavailableAppleCredentialProvider(),
          ),
        ],
        child: const EmsalistApp(),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byType(LoginScreen), findsOneWidget);
    expect(find.text('Giriş Yap'), findsOneWidget);
  });

  testWidgets('authenticated user lands in the app shell, not login', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(authenticatedApp());
    await tester.pumpAndSettle();

    expect(find.byType(LoginScreen), findsNothing);
    expect(find.byType(NavigationBar), findsOneWidget);
  });

  testWidgets('app restart restores a persisted session', (
    WidgetTester tester,
  ) async {
    // A persisted session in the fake store simulates a prior login surviving
    // an app restart.
    final FakeSecureSessionStore store = FakeSecureSessionStore(kTestSession);
    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          secureSessionStoreProvider.overrideWithValue(store),
          appleCredentialProvider.overrideWithValue(
            const UnavailableAppleCredentialProvider(),
          ),
        ],
        child: const EmsalistApp(),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byType(LoginScreen), findsNothing);
    expect(find.byType(NavigationBar), findsOneWidget);
  });

  testWidgets('Apple button hidden when provider is unavailable', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          secureSessionStoreProvider.overrideWithValue(
            FakeSecureSessionStore(),
          ),
          appleCredentialProvider.overrideWithValue(
            const UnavailableAppleCredentialProvider(),
          ),
        ],
        child: const EmsalistApp(),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Apple ile Devam Et'), findsNothing);
  });
}
