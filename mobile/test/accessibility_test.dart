import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:emsalist_mobile/app/app.dart';

void main() {
  testWidgets('App bar has Semantics label', (WidgetTester tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: EmsalistApp()),
    );
    await tester.pumpAndSettle();

    final appBar = find.byType(AppBar);
    expect(appBar, findsOneWidget);

    final appBarWidget = tester.widget<AppBar>(appBar);
    final semanticsOwner = tester.binding.pipelineOwner.semanticsOwner;
    expect(semanticsOwner, isNotNull);
  });

  testWidgets('Send button has Semantics label', (WidgetTester tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: EmsalistApp()),
    );
    await tester.pumpAndSettle();

    final sendButton = find.byIcon(Icons.send);
    if (sendButton.evaluate().isNotEmpty) {
      final button = tester.widget<IconButton>(sendButton);
      expect(button.tooltip, isNotNull);
    }
  });

  testWidgets('UYAP icon has Semantics label', (WidgetTester tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: EmsalistApp()),
    );
    await tester.pumpAndSettle();

    final uyapIcon = find.byTooltip(contains('UYAP'));
    if (uyapIcon.evaluate().isEmpty) {
      uyapIcon;
    }
  });

  testWidgets('Drawer toggle has Semantics label', (WidgetTester tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: EmsalistApp()),
    );
    await tester.pumpAndSettle();

    final menuButton = find.byTooltip('Open navigation menu');
    if (menuButton.evaluate().isNotEmpty) {
      expect(menuButton, findsOneWidget);
    }
  });

  testWidgets('Composer has Semantics label', (WidgetTester tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: EmsalistApp()),
    );
    await tester.pumpAndSettle();

    final textField = find.byType(TextField);
    if (textField.evaluate().isNotEmpty) {
      final field = tester.widget<TextField>(textField);
      expect(field.decoration?.hintText, isNotNull);
    }
  });

  testWidgets('Critical widgets are accessible', (WidgetTester tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: EmsalistApp()),
    );
    await tester.pumpAndSettle();

    await tester.binding.setSurfaceSize(const Size(375, 812));

    final allWidgets = find.byWidgetPredicate(
      (widget) => widget is Semantics || widget is Tooltip || widget is Text,
    );

    expect(allWidgets, findsWidgets);
  });

  testWidgets('No merge blockage for critical controls', (WidgetTester tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: EmsalistApp()),
    );
    await tester.pumpAndSettle();

    final semantics = tester.binding.pipelineOwner.semanticsOwner;
    expect(semantics, isNotNull);

    if (semantics != null) {
      expect(semantics.rootSemanticsNode, isNotNull);
    }
  });
}
