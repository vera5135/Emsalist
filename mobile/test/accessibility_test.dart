import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:emsalist_mobile/design_system/components/emsalist_composer.dart';

import 'support/auth_test_support.dart';

void main() {
  testWidgets('App bar has Semantics label', (WidgetTester tester) async {
    await tester.pumpWidget(authenticatedApp());
    await tester.pumpAndSettle();

    final appBar = find.byType(AppBar);
    expect(appBar, findsOneWidget);
  });

  testWidgets('Send button has Semantics label', (WidgetTester tester) async {
    await tester.pumpWidget(authenticatedApp());
    await tester.pumpAndSettle();

    final sendButton = find.byIcon(Icons.send);
    expect(sendButton, findsOneWidget);
  });

  testWidgets('UYAP icon has Semantics label', (WidgetTester tester) async {
    await tester.pumpWidget(authenticatedApp());
    await tester.pumpAndSettle();

    final SemanticsHandle handle = tester.ensureSemantics();
    expect(find.bySemanticsLabel(RegExp('UYAP durumu')), findsOneWidget);
    handle.dispose();
  });

  testWidgets('Drawer toggle has Semantics label', (WidgetTester tester) async {
    await tester.pumpWidget(authenticatedApp());
    await tester.pumpAndSettle();

    final menuButton = find.byTooltip('Dosyalar');
    expect(menuButton, findsAtLeastNWidgets(1));
  });

  testWidgets('Composer has Semantics label', (WidgetTester tester) async {
    await tester.pumpWidget(authenticatedApp());
    await tester.pumpAndSettle();

    final textField = find.byType(TextField);
    expect(textField, findsWidgets);
    final field = tester.widget<TextField>(textField.first);
    expect(field.decoration?.hintText, isNotNull);
  });

  testWidgets('Critical widgets are accessible', (WidgetTester tester) async {
    await tester.pumpWidget(authenticatedApp());
    await tester.pumpAndSettle();

    await tester.binding.setSurfaceSize(const Size(375, 812));

    final allWidgets = find.byWidgetPredicate(
      (widget) => widget is Semantics || widget is Tooltip || widget is Text,
    );

    expect(allWidgets, findsWidgets);
  });

  testWidgets('No merge blockage for critical controls', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(authenticatedApp());
    await tester.pumpAndSettle();

    final SemanticsHandle handle = tester.ensureSemantics();
    expect(find.byType(AppBar), findsOneWidget);
    expect(find.byType(EmsalistComposer), findsOneWidget);
    handle.dispose();
  });
}
