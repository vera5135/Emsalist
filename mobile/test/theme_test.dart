import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:emsalist_mobile/core/providers/theme_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'support/auth_test_support.dart';

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  testWidgets('Default theme mode is system', (WidgetTester tester) async {
    await tester.pumpWidget(authenticatedApp());
    await tester.pumpAndSettle();

    final materialApp = tester.widget<MaterialApp>(find.byType(MaterialApp));
    expect(materialApp.themeMode, equals(ThemeMode.system));
  });

  testWidgets('Switching to light theme via provider', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(authenticatedApp());
    await tester.pumpAndSettle();

    final container = ProviderScope.containerOf(
      tester.element(find.byType(MaterialApp)),
    );
    container.read(themeModeProvider.notifier).setThemeMode(ThemeMode.light);
    await tester.pumpAndSettle();

    final materialApp = tester.widget<MaterialApp>(find.byType(MaterialApp));
    expect(materialApp.themeMode, equals(ThemeMode.light));
  });

  testWidgets('Switching to dark theme via provider', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(authenticatedApp());
    await tester.pumpAndSettle();

    final container = ProviderScope.containerOf(
      tester.element(find.byType(MaterialApp)),
    );
    container.read(themeModeProvider.notifier).setThemeMode(ThemeMode.dark);
    await tester.pumpAndSettle();

    final materialApp = tester.widget<MaterialApp>(find.byType(MaterialApp));
    expect(materialApp.themeMode, equals(ThemeMode.dark));
  });

  testWidgets('Theme mode persists via provider state', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(authenticatedApp());
    await tester.pumpAndSettle();

    final container = ProviderScope.containerOf(
      tester.element(find.byType(MaterialApp)),
    );
    final notifier = container.read(themeModeProvider.notifier);

    notifier.setThemeMode(ThemeMode.dark);
    await tester.pumpAndSettle();

    final state = container.read(themeModeProvider);
    expect(state, equals(ThemeMode.dark));

    notifier.setThemeMode(ThemeMode.light);
    await tester.pumpAndSettle();

    final state2 = container.read(themeModeProvider);
    expect(state2, equals(ThemeMode.light));
  });

  testWidgets('MaterialApp theme is available', (WidgetTester tester) async {
    await tester.pumpWidget(authenticatedApp());
    await tester.pumpAndSettle();

    final materialApp = tester.widget<MaterialApp>(find.byType(MaterialApp));
    expect(materialApp.theme, isNotNull);
    expect(materialApp.darkTheme, isNotNull);
    expect(materialApp.themeMode, isNotNull);
    expect(materialApp.theme?.useMaterial3, isTrue);
  });
}
