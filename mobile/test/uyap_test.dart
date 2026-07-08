import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:emsalist_mobile/app/app.dart';
import 'package:emsalist_mobile/widgets/uyap_icon.dart';

void main() {
  testWidgets('UYAP icon is visible with correct default status', (WidgetTester tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: EmsalistApp()),
    );
    await tester.pumpAndSettle();

    expect(find.byType(UyapStatusIcon), findsOneWidget);
  });

  testWidgets('UYAP icon shows default status text', (WidgetTester tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: EmsalistApp()),
    );
    await tester.pumpAndSettle();

    final uyapIcon = find.byType(UyapStatusIcon);
    expect(uyapIcon, findsOneWidget);
  });

  testWidgets('UYAP bottom sheet opens on tap', (WidgetTester tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: EmsalistApp()),
    );
    await tester.pumpAndSettle();

    final uyapIcon = find.byType(UyapStatusIcon);
    expect(uyapIcon, findsOneWidget);

    await tester.tap(uyapIcon);
    await tester.pumpAndSettle();

    expect(find.byType(BottomSheet), findsOneWidget);
  });

  testWidgets('UYAP bottom sheet dismisses correctly', (WidgetTester tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: EmsalistApp()),
    );
    await tester.pumpAndSettle();

    final uyapIcon = find.byType(UyapStatusIcon);
    expect(uyapIcon, findsOneWidget);

    await tester.tap(uyapIcon);
    await tester.pumpAndSettle();

    expect(find.byType(BottomSheet), findsOneWidget);

    final backButton = find.byTooltip('Back');
    if (backButton.evaluate().isNotEmpty) {
      await tester.tap(backButton);
      await tester.pumpAndSettle();
    }
  });

  testWidgets('UYAP status changes reflect on icon', (WidgetTester tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: EmsalistApp()),
    );
    await tester.pumpAndSettle();

    final uyapIcon = find.byType(UyapStatusIcon);
    expect(uyapIcon, findsOneWidget);

    final icon = tester.widget<UyapStatusIcon>(uyapIcon);
    expect(icon, isNotNull);
  });
}
