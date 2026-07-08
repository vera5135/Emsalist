import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:emsalist_mobile/app/app.dart';

void main() {
  testWidgets('App opens without crashing', (WidgetTester tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: EmsalistApp()),
    );

    await tester.pumpAndSettle();

    expect(find.byType(MaterialApp), findsOneWidget);
  });

  testWidgets('ProviderScope wraps the app correctly', (WidgetTester tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: EmsalistApp()),
    );

    await tester.pump();

    expect(find.byType(EmsalistApp), findsOneWidget);
  });

  testWidgets('App renders initial route without errors', (WidgetTester tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: EmsalistApp()),
    );

    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
  });

  testWidgets('App has a Scaffold at root', (WidgetTester tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: EmsalistApp()),
    );

    await tester.pumpAndSettle();

    expect(find.byType(Scaffold), findsAtLeastNWidgets(1));
  });
}
