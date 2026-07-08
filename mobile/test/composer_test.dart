import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:emsalist_mobile/app/app.dart';
import 'package:emsalist_mobile/design_system/components/emsalist_composer.dart';

void main() {
  testWidgets('EmsalistComposer renders text field and add button', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(const ProviderScope(child: EmsalistApp()));
    await tester.pumpAndSettle();

    expect(find.byType(EmsalistComposer), findsOneWidget);
    expect(find.byType(TextField), findsWidgets);
    expect(find.byIcon(Icons.add_circle_outline), findsOneWidget);
  });

  testWidgets('Empty message — send button disabled', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(const ProviderScope(child: EmsalistApp()));
    await tester.pumpAndSettle();

    final sendButton = find.byIcon(Icons.send);
    expect(sendButton, findsOneWidget);

    final IconButton button = tester.widget<IconButton>(
      find.ancestor(of: sendButton, matching: find.byType(IconButton)),
    );
    expect(button.onPressed, isNull);
  });

  testWidgets('Typing enables send and clears input on send', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(const ProviderScope(child: EmsalistApp()));
    await tester.pumpAndSettle();

    final textField = find.byType(TextField).first;
    expect(textField, findsOneWidget);
    await tester.enterText(textField, 'Merhaba dünya');
    await tester.pumpAndSettle();

    final sendButton = find.byIcon(Icons.send);
    final IconButton button = tester.widget<IconButton>(
      find.ancestor(of: sendButton, matching: find.byType(IconButton)),
    );
    expect(button.onPressed, isNotNull);

    await tester.tap(sendButton);
    await tester.pumpAndSettle();

    final TextField field = tester.widget<TextField>(textField);
    expect(field.controller?.text ?? '', isEmpty);
    expect(find.text('Merhaba dünya'), findsWidgets);
  });

  testWidgets('+ menu shows all 6 options', (WidgetTester tester) async {
    await tester.pumpWidget(const ProviderScope(child: EmsalistApp()));
    await tester.pumpAndSettle();

    final attachButton = find.byIcon(Icons.add_circle_outline);
    expect(attachButton, findsOneWidget);
    await tester.tap(attachButton);
    await tester.pumpAndSettle();

    expect(find.text('Belge Yükle'), findsOneWidget);
    expect(find.text('Fotoğraf Çek'), findsOneWidget);
    expect(find.text('Galeriden Ekle'), findsOneWidget);
    expect(find.text('UYAP Evrakı Ekle'), findsOneWidget);
    expect(find.text('İçtihat Ara'), findsOneWidget);
    expect(find.text('Dilekçe Hazırla'), findsOneWidget);
  });
}
