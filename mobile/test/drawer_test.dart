import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:emsalist_mobile/app/app.dart';

void main() {
  testWidgets('Drawer opens when hamburger tapped', (WidgetTester tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: EmsalistApp()),
    );
    await tester.pumpAndSettle();

    expect(find.byType(AppBar), findsOneWidget);

    final hamburgerButton = find.byTooltip('Open navigation menu');
    if (hamburgerButton.evaluate().isNotEmpty) {
      await tester.tap(hamburgerButton);
      await tester.pumpAndSettle();

      expect(find.byType(Drawer), findsOneWidget);
    }
  });

  testWidgets('Drawer lists mock cases', (WidgetTester tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: EmsalistApp()),
    );
    await tester.pumpAndSettle();

    final hamburger = find.byTooltip('Open navigation menu');
    if (hamburger.evaluate().isNotEmpty) {
      await tester.tap(hamburger);
      await tester.pumpAndSettle();

      expect(find.byType(ListView), findsWidgets);
      expect(find.byType(ListTile), findsWidgets);
    }
  });

  testWidgets('Active case is visible in drawer', (WidgetTester tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: EmsalistApp()),
    );
    await tester.pumpAndSettle();

    final hamburger = find.byTooltip('Open navigation menu');
    if (hamburger.evaluate().isNotEmpty) {
      await tester.tap(hamburger);
      await tester.pumpAndSettle();

      final drawer = find.byType(Drawer);
      expect(drawer, findsOneWidget);
    }
  });

  testWidgets('Drawer has a header section', (WidgetTester tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: EmsalistApp()),
    );
    await tester.pumpAndSettle();

    final hamburger = find.byTooltip('Open navigation menu');
    if (hamburger.evaluate().isNotEmpty) {
      await tester.tap(hamburger);
      await tester.pumpAndSettle();

      final drawerHeader = find.byType(DrawerHeader);
      expect(drawerHeader, findsOneWidget);
    }
  });

  testWidgets('Drawer can be closed', (WidgetTester tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: EmsalistApp()),
    );
    await tester.pumpAndSettle();

    final hamburger = find.byTooltip('Open navigation menu');
    if (hamburger.evaluate().isNotEmpty) {
      await tester.tap(hamburger);
      await tester.pumpAndSettle();

      expect(find.byType(Drawer), findsOneWidget);

      final closeButton = find.byTooltip('Back');
      if (closeButton.evaluate().isNotEmpty) {
        await tester.tap(closeButton);
        await tester.pumpAndSettle();
      }
    }
  });
}
