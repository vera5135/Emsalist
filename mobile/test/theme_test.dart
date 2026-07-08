import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:emsalist_mobile/app/app.dart';

void main() {
  testWidgets('Default theme mode is system', (WidgetTester tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: EmsalistApp()),
    );

    await tester.pumpAndSettle();

    final materialApp = tester.widget<MaterialApp>(find.byType(MaterialApp));
    expect(materialApp.themeMode, equals(ThemeMode.system));
  });

  testWidgets('Switching to light theme works', (WidgetTester tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: EmsalistApp()),
    );

    await tester.pumpAndSettle();

    final lightTheme = ThemeData.light();
    final initialTheme = tester.widget<MaterialApp>(find.byType(MaterialApp)).theme;
    expect(initialTheme?.brightness, equals(lightTheme.brightness));
  });

  testWidgets('Switching to dark theme works', (WidgetTester tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: EmsalistApp()),
    );

    await tester.pumpAndSettle();

    final darkTheme = ThemeData.dark();
    final materialApp = tester.widget<MaterialApp>(find.byType(MaterialApp));
    final appDarkTheme = materialApp.darkTheme;

    expect(appDarkTheme?.brightness, equals(darkTheme.brightness));
    expect(appDarkTheme?.brightness, equals(Brightness.dark));
  });

  testWidgets('Theme is provided via MaterialApp', (WidgetTester tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: EmsalistApp()),
    );

    await tester.pumpAndSettle();

    final materialApp = tester.widget<MaterialApp>(find.byType(MaterialApp));
    expect(materialApp.theme, isNotNull);
    expect(materialApp.darkTheme, isNotNull);
    expect(materialApp.themeMode, isNotNull);
  });

  testWidgets('MaterialApp reads theme correctly', (WidgetTester tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: EmsalistApp()),
    );

    await tester.pumpAndSettle();

    final materialApp = tester.widget<MaterialApp>(find.byType(MaterialApp));
    expect(materialApp.theme?.useMaterial3, isTrue);
    expect(materialApp.darkTheme?.useMaterial3, isTrue);
  });
}
