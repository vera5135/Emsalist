import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:emsalist_mobile/features/uyap/uyap_status_icon.dart';

import 'support/auth_test_support.dart';

void main() {
  testWidgets('UYAP icon is visible with correct default status', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(authenticatedApp());
    await tester.pumpAndSettle();

    expect(find.byType(UyapStatusIcon), findsOneWidget);
  });

  testWidgets('UYAP bottom sheet opens on tap', (WidgetTester tester) async {
    await tester.pumpWidget(authenticatedApp());
    await tester.pumpAndSettle();

    final uyapIcon = find.byType(UyapStatusIcon);
    expect(uyapIcon, findsOneWidget);

    await tester.tap(uyapIcon);
    await tester.pumpAndSettle();

    expect(find.byType(BottomSheet), findsOneWidget);
  });

  testWidgets('UYAP bottom sheet dismisses correctly', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(authenticatedApp());
    await tester.pumpAndSettle();

    final uyapIcon = find.byType(UyapStatusIcon);
    expect(uyapIcon, findsOneWidget);

    await tester.tap(uyapIcon);
    await tester.pumpAndSettle();

    expect(find.byType(BottomSheet), findsOneWidget);

    await tester.tapAt(const Offset(10, 10));
    await tester.pumpAndSettle();
  });
}
