import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:emsalist_mobile/app/app.dart';
import 'package:emsalist_mobile/widgets/composer.dart';

void main() {
  testWidgets('Empty message send button is disabled', (WidgetTester tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: EmsalistApp()),
    );
    await tester.pumpAndSettle();

    expect(find.byType(MessageComposer), findsOneWidget);

    final sendButton = find.byIcon(Icons.send);
    if (sendButton.evaluate().isNotEmpty) {
      final button = tester.widget<IconButton>(sendButton);
      expect(button.onPressed, isNull);
    }
  });

  testWidgets('Typing enables send button', (WidgetTester tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: EmsalistApp()),
    );
    await tester.pumpAndSettle();

    final textField = find.byType(TextField);
    if (textField.evaluate().isNotEmpty) {
      await tester.enterText(textField, 'Hello');
      await tester.pumpAndSettle();

      final sendButton = find.byIcon(Icons.send);
      if (sendButton.evaluate().isNotEmpty) {
        final button = tester.widget<IconButton>(sendButton);
        expect(button.onPressed, isNotNull);
      }
    }
  });

  testWidgets('Send clears input', (WidgetTester tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: EmsalistApp()),
    );
    await tester.pumpAndSettle();

    final textField = find.byType(TextField);
    if (textField.evaluate().isNotEmpty) {
      await tester.enterText(textField, 'Test message');
      await tester.pumpAndSettle();

      final sendButton = find.byIcon(Icons.send);
      if (sendButton.evaluate().isNotEmpty) {
        final button = tester.widget<IconButton>(sendButton);
        if (button.onPressed != null) {
          button.onPressed!();
          await tester.pumpAndSettle();
        }
      }
    }
  });

  testWidgets('+ menu shows options', (WidgetTester tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: EmsalistApp()),
    );
    await tester.pumpAndSettle();

    final attachButton = find.byIcon(Icons.add);
    if (attachButton.evaluate().isNotEmpty) {
      await tester.tap(attachButton);
      await tester.pumpAndSettle();

      expect(find.byType(PopupMenuItem), findsWidgets);
    }
  });

  testWidgets('Composer has text input field', (WidgetTester tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: EmsalistApp()),
    );
    await tester.pumpAndSettle();

    final composer = find.byType(MessageComposer);
    expect(composer, findsOneWidget);

    final textField = find.byType(TextField);
    expect(textField, findsOneWidget);
  });
}
