import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:emsalist_mobile/app/app.dart';
import 'package:emsalist_mobile/features/uyap/uyap_status_icon.dart';

const List<Size> _deviceSizes = <Size>[
  Size(375, 812),
  Size(390, 844),
  Size(430, 932),
];

Future<void> _pumpAt(WidgetTester tester, Size size) async {
  tester.view.physicalSize = size * 3.0;
  tester.view.devicePixelRatio = 3.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);

  await tester.pumpWidget(const ProviderScope(child: EmsalistApp()));
  await tester.pumpAndSettle();
}

void main() {
  for (final Size size in _deviceSizes) {
    final String label = '${size.width.toInt()}x${size.height.toInt()}';

    testWidgets('No overflow on $label', (WidgetTester tester) async {
      await _pumpAt(tester, size);
      expect(tester.takeException(), isNull);
      expect(find.byType(AppBar), findsAtLeastNWidgets(1));
      expect(find.byType(Scaffold), findsAtLeastNWidgets(1));
    });

    testWidgets('Drawer has no overflow on $label', (
      WidgetTester tester,
    ) async {
      await _pumpAt(tester, size);

      await tester.tap(find.byIcon(Icons.menu).first);
      await tester.pumpAndSettle();

      expect(find.byType(Drawer), findsAtLeastNWidgets(1));
      expect(tester.takeException(), isNull);
    });

    testWidgets('UYAP sheet has no overflow on $label', (
      WidgetTester tester,
    ) async {
      await _pumpAt(tester, size);

      await tester.tap(find.byType(UyapStatusIcon));
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
    });

    testWidgets('Composer visible with keyboard inset on $label', (
      WidgetTester tester,
    ) async {
      tester.view.physicalSize = size * 3.0;
      tester.view.devicePixelRatio = 3.0;
      tester.view.viewInsets = const FakeViewPadding(bottom: 336 * 3.0);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      addTearDown(tester.view.resetViewInsets);

      await tester.pumpWidget(const ProviderScope(child: EmsalistApp()));
      await tester.pumpAndSettle();

      expect(find.byType(TextField), findsWidgets);
      expect(find.byIcon(Icons.send), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets('High Dynamic Type has no overflow', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(375, 812) * 3.0;
    tester.view.devicePixelRatio = 3.0;
    tester.platformDispatcher.textScaleFactorTestValue = 1.5;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);

    await tester.pumpWidget(const ProviderScope(child: EmsalistApp()));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
  });
}
