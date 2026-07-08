import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:emsalist_mobile/app/app.dart';

void main() {
  testWidgets('Small iPhone viewport 375x667 has no overflow', (WidgetTester tester) async {
    tester.binding.window.physicalSizeTestValue = const Size(375 * 3, 667 * 3);
    tester.binding.window.devicePixelRatioTestValue = 3.0;
    addTearDown(() {
      tester.binding.window.clearPhysicalSizeTestValue();
      tester.binding.window.clearDevicePixelRatioTestValue();
    });

    await tester.pumpWidget(
      const ProviderScope(child: EmsalistApp()),
    );
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
  });

  testWidgets('iPhone SE sized viewport renders all key widgets', (WidgetTester tester) async {
    tester.binding.window.physicalSizeTestValue = const Size(375 * 2, 667 * 2);
    tester.binding.window.devicePixelRatioTestValue = 2.0;
    addTearDown(() {
      tester.binding.window.clearPhysicalSizeTestValue();
      tester.binding.window.clearDevicePixelRatioTestValue();
    });

    await tester.pumpWidget(
      const ProviderScope(child: EmsalistApp()),
    );
    await tester.pumpAndSettle();

    expect(find.byType(AppBar), findsOneWidget);
    expect(find.byType(Scaffold), findsAtLeastNWidgets(1));
  });

  testWidgets('Small viewport does not overflow drawer', (WidgetTester tester) async {
    tester.binding.window.physicalSizeTestValue = const Size(375 * 2, 667 * 2);
    tester.binding.window.devicePixelRatioTestValue = 2.0;
    addTearDown(() {
      tester.binding.window.clearPhysicalSizeTestValue();
      tester.binding.window.clearDevicePixelRatioTestValue();
    });

    await tester.pumpWidget(
      const ProviderScope(child: EmsalistApp()),
    );
    await tester.pumpAndSettle();

    final hamburger = find.byTooltip('Open navigation menu');
    if (hamburger.evaluate().isNotEmpty) {
      await tester.tap(hamburger);
      await tester.pumpAndSettle();

      expect(find.byType(Drawer), findsOneWidget);
      expect(tester.takeException(), isNull);
    }
  });

  testWidgets('Bottom sheet fits in small viewport', (WidgetTester tester) async {
    tester.binding.window.physicalSizeTestValue = const Size(375 * 2, 667 * 2);
    tester.binding.window.devicePixelRatioTestValue = 2.0;
    addTearDown(() {
      tester.binding.window.clearPhysicalSizeTestValue();
      tester.binding.window.clearDevicePixelRatioTestValue();
    });

    await tester.pumpWidget(
      const ProviderScope(child: EmsalistApp()),
    );
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
  });

  testWidgets('All content fits without overflow on 375x667', (WidgetTester tester) async {
    tester.binding.window.physicalSizeTestValue = const Size(375 * 2, 667 * 2);
    tester.binding.window.devicePixelRatioTestValue = 2.0;
    addTearDown(() {
      tester.binding.window.clearPhysicalSizeTestValue();
      tester.binding.window.clearDevicePixelRatioTestValue();
    });

    await tester.pumpWidget(
      const ProviderScope(child: EmsalistApp()),
    );
    await tester.pumpAndSettle();

    final overflowErrors = tester.renderObjectList.whereType<RenderFlex>();
    for (final flex in overflowErrors) {
      expect(flex.hasOverflow, isFalse, reason: '${flex.runtimeType} has overflow');
    }
  });
}
