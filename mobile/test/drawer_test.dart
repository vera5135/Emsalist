import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:emsalist_mobile/app/app.dart';

void main() {
  testWidgets('Drawer opens when hamburger tapped', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(const ProviderScope(child: EmsalistApp()));
    await tester.pumpAndSettle();

    expect(find.byType(AppBar), findsAtLeastNWidgets(1));

    final hamburger = find.byIcon(Icons.menu);
    expect(hamburger, findsAtLeastNWidgets(1));
    await tester.tap(hamburger);
    await tester.pumpAndSettle();

    expect(find.byType(Drawer), findsAtLeastNWidgets(1));
  });

  testWidgets('Drawer lists mock cases', (WidgetTester tester) async {
    await tester.pumpWidget(const ProviderScope(child: EmsalistApp()));
    await tester.pumpAndSettle();

    final hamburger = find.byIcon(Icons.menu);
    expect(hamburger, findsAtLeastNWidgets(1));
    await tester.tap(hamburger);
    await tester.pumpAndSettle();

    expect(find.byType(ListView), findsWidgets);
    expect(find.byType(ListTile), findsWidgets);
  });

  testWidgets('Active case is visible in drawer', (WidgetTester tester) async {
    await tester.pumpWidget(const ProviderScope(child: EmsalistApp()));
    await tester.pumpAndSettle();

    final hamburger = find.byIcon(Icons.menu);
    expect(hamburger, findsAtLeastNWidgets(1));
    await tester.tap(hamburger);
    await tester.pumpAndSettle();

    expect(find.byType(Drawer), findsAtLeastNWidgets(1));
  });

  testWidgets('Drawer has search and new case button', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(const ProviderScope(child: EmsalistApp()));
    await tester.pumpAndSettle();

    final hamburger = find.byIcon(Icons.menu);
    await tester.tap(hamburger);
    await tester.pumpAndSettle();

    expect(find.text('Yeni Dosya'), findsOneWidget);
    expect(find.byType(TextField), findsAtLeastNWidgets(1));
  });

  testWidgets('Drawer can be closed', (WidgetTester tester) async {
    await tester.pumpWidget(const ProviderScope(child: EmsalistApp()));
    await tester.pumpAndSettle();

    final hamburger = find.byIcon(Icons.menu);
    expect(hamburger, findsAtLeastNWidgets(1));
    await tester.tap(hamburger.first);
    await tester.pumpAndSettle();

    expect(find.byType(Drawer), findsAtLeastNWidgets(1));

    final ScaffoldState scaffold = tester.state(
      find
          .ancestor(of: find.byType(AppBar), matching: find.byType(Scaffold))
          .first,
    );
    scaffold.closeDrawer();
    await tester.pumpAndSettle();

    expect(find.byType(Drawer), findsNothing);
  });
}
