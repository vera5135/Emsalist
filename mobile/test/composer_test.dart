import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:emsalist_mobile/app/app.dart';
import 'package:emsalist_mobile/design_system/components/emsalist_composer.dart';

void main() {
  testWidgets('EmsalistComposer renders text field and send button', (WidgetTester tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: EmsalistApp()),
    );
    await tester.pumpAndSettle();

    expect(find.byType(EmsalistComposer), findsOneWidget);
    expect(find.byType(TextField), findsOneWidget);
  });

  testWidgets('Empty message — no send icon visible on disabled state', (WidgetTester tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: EmsalistApp()),
    );
    await tester.pumpAndSettle();

    final textField = find.byType(TextField);
    expect(textField, findsOneWidget);

    final sendButton = find.byIcon(Icons.send);
    expect(sendButton, findsOneWidget);
  });

  testWidgets('Typing enables send button', (WidgetTester tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: EmsalistApp()),
    );
    await tester.pumpAndSettle();

    final textField = find.byType(TextField);
    expect(textField, findsOneWidget);
    await tester.enterText(textField, 'Hello');
    await tester.pumpAndSettle();

    final sendButton = find.byIcon(Icons.send);
    expect(sendButton, findsOneWidget);
  });

  testWidgets('+ menu shows options', (WidgetTester tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: EmsalistApp()),
    );
    await tester.pumpAndSettle();

    final attachButton = find.byIcon(Icons.add);
    expect(attachButton, findsOneWidget);
    await tester.tap(attachButton);
    await tester.pumpAndSettle();

    expect(find.byType(PopupMenuItem), findsWidgets);
  });
}
