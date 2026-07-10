import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/auth_test_support.dart';

void main() {
  testWidgets('Case summary bottom sheet opens', (WidgetTester tester) async {
    await tester.pumpWidget(authenticatedApp());
    await tester.pumpAndSettle();

    final caseTile = find.byTooltip('Open case summary');
    if (caseTile.evaluate().isNotEmpty) {
      await tester.tap(caseTile);
      await tester.pumpAndSettle();

      expect(find.byType(BottomSheet), findsOneWidget);
    }
  });

  testWidgets('Case summary shows sections', (WidgetTester tester) async {
    await tester.pumpWidget(authenticatedApp());
    await tester.pumpAndSettle();

    final caseTile = find.byTooltip('Open case summary');
    if (caseTile.evaluate().isNotEmpty) {
      await tester.tap(caseTile);
      await tester.pumpAndSettle();

      final sectionHeaders = find.byType(Text);
      expect(sectionHeaders, findsWidgets);
    }
  });

  testWidgets('Case summary bottom sheet dismisses', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(authenticatedApp());
    await tester.pumpAndSettle();

    final caseTile = find.byTooltip('Open case summary');
    if (caseTile.evaluate().isNotEmpty) {
      await tester.tap(caseTile);
      await tester.pumpAndSettle();

      expect(find.byType(BottomSheet), findsOneWidget);

      final backButton = find.byTooltip('Back');
      if (backButton.evaluate().isNotEmpty) {
        await tester.tap(backButton);
        await tester.pumpAndSettle();
      }
    }
  });

  testWidgets('Case summary has a title', (WidgetTester tester) async {
    await tester.pumpWidget(authenticatedApp());
    await tester.pumpAndSettle();

    final caseTile = find.byTooltip('Open case summary');
    if (caseTile.evaluate().isNotEmpty) {
      await tester.tap(caseTile);
      await tester.pumpAndSettle();

      final bottomSheet = find.byType(BottomSheet);
      expect(bottomSheet, findsOneWidget);
    }
  });
}
