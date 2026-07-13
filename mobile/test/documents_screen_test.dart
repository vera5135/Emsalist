import 'dart:typed_data';

import 'package:emsalist_mobile/features/documents/application/document_providers.dart';
import 'package:emsalist_mobile/features/documents/data/document_api.dart';
import 'package:emsalist_mobile/features/documents/data/document_picker.dart';
import 'package:emsalist_mobile/features/documents/data/document_repository.dart';
import 'package:emsalist_mobile/features/documents/presentation/documents_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_api_client.dart';

const String _caseId = 'c1';
const String _base = '/api/v1/cases/$_caseId/documents';

class _FakeDocumentPicker implements DocumentPicker {
  _FakeDocumentPicker(this.result);

  final PickedDocument? result;
  int calls = 0;

  @override
  Future<PickedDocument?> pickDocument() async {
    calls += 1;
    return result;
  }
}

Widget _host(FakeApiClient client, {DocumentPicker? picker}) {
  return ProviderScope(
    overrides: <Override>[
      documentRepositoryProvider.overrideWithValue(
        DocumentRepository(DocumentApi(client)),
      ),
      if (picker != null) documentPickerProvider.overrideWithValue(picker),
    ],
    child: const MaterialApp(home: DocumentsScreen(caseId: _caseId)),
  );
}

Map<String, dynamic> _doc({
  String id = 'd1',
  String status = 'analyzed',
  String support = 'fully_supported',
  String name = 'sozlesme.txt',
}) {
  return <String, dynamic>{
    'id': id,
    'case_id': _caseId,
    'original_filename': name,
    'extension': '.txt',
    'size_bytes': 2048,
    'status': status,
    'support_level': support,
    'page_count': 1,
    'extracted_text_available': true,
    'version': 1,
  };
}

void main() {
  testWidgets('picker cancellation leaves upload flow unchanged', (
    WidgetTester tester,
  ) async {
    final FakeApiClient client = FakeApiClient()
      ..whenGet(_base, <String, dynamic>{
        'items': <dynamic>[],
        'total': 0,
        'has_more': false,
      });
    final _FakeDocumentPicker picker = _FakeDocumentPicker(null);

    await tester.pumpWidget(_host(client, picker: picker));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Belge Ekle'));
    await tester.pumpAndSettle();

    expect(picker.calls, 1);
    expect(client.uploadPaths, isEmpty);
    expect(find.byType(SnackBar), findsNothing);
  });

  testWidgets('native picker uploads selected file bytes', (
    WidgetTester tester,
  ) async {
    final FakeApiClient client = FakeApiClient()
      ..whenGet(_base, <String, dynamic>{
        'items': <dynamic>[],
        'total': 0,
        'has_more': false,
      })
      ..whenPost(_base, _doc(name: 'sozlesme.pdf'));
    final _FakeDocumentPicker picker = _FakeDocumentPicker(
      PickedDocument(
        bytes: Uint8List.fromList(<int>[0x25, 0x50, 0x44, 0x46]),
        filename: 'sozlesme.pdf',
        mimeType: 'application/pdf',
      ),
    );

    await tester.pumpWidget(_host(client, picker: picker));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Belge Ekle'));
    await tester.pumpAndSettle();

    expect(picker.calls, 1);
    expect(client.uploadPaths, contains(_base));
    expect(
      client.uploadBodies.single,
      containsPair('filename', 'sozlesme.pdf'),
    );
  });

  testWidgets('empty state when no documents', (WidgetTester tester) async {
    final FakeApiClient client = FakeApiClient()
      ..whenGet(_base, <String, dynamic>{
        'items': <dynamic>[],
        'total': 0,
        'has_more': false,
      });

    await tester.pumpWidget(_host(client));
    await tester.pumpAndSettle();

    expect(find.text('Henüz belge yok'), findsOneWidget);
    expect(find.text('Belge Ekle'), findsOneWidget);
  });

  testWidgets('error state with retry', (WidgetTester tester) async {
    final FakeApiClient client = FakeApiClient()
      ..whenGetError(_base, StateError('boom'));

    await tester.pumpWidget(_host(client));
    await tester.pumpAndSettle();

    expect(find.text('Tekrar Dene'), findsOneWidget);
  });

  testWidgets('renders document card with completed status', (
    WidgetTester tester,
  ) async {
    final FakeApiClient client = FakeApiClient()
      ..whenGet(_base, <String, dynamic>{
        'items': <dynamic>[_doc()],
        'total': 1,
        'has_more': false,
      });

    await tester.pumpWidget(_host(client));
    await tester.pumpAndSettle();

    expect(find.text('sozlesme.txt'), findsOneWidget);
    expect(find.text('İnceleme tamamlandı'), findsOneWidget);
  });

  testWidgets('unsupported image card shows non-technical message', (
    WidgetTester tester,
  ) async {
    final FakeApiClient client = FakeApiClient()
      ..whenGet(_base, <String, dynamic>{
        'items': <dynamic>[
          _doc(
            id: 'd2',
            status: 'unsupported',
            support: 'upload_only',
            name: 'foto.png',
          ),
        ],
        'total': 1,
        'has_more': false,
      });

    await tester.pumpWidget(_host(client));
    await tester.pumpAndSettle();

    expect(find.text('Bu dosya türü henüz analiz edilemiyor'), findsOneWidget);
  });

  testWidgets('processing card shows progress + reviewing text', (
    WidgetTester tester,
  ) async {
    final FakeApiClient client = FakeApiClient()
      ..whenGet(_base, <String, dynamic>{
        'items': <dynamic>[_doc(status: 'processing')],
        'total': 1,
        'has_more': false,
      });

    await tester.pumpWidget(_host(client));
    await tester.pump(); // don't settle: keep the CircularProgressIndicator

    expect(find.text('Belge inceleniyor'), findsOneWidget);
  });

  testWidgets('analysis screen renders extractions with page provenance', (
    WidgetTester tester,
  ) async {
    final FakeApiClient client = FakeApiClient()
      ..whenGet(_base, <String, dynamic>{
        'items': <dynamic>[_doc(status: 'awaiting_confirmation')],
        'total': 1,
        'has_more': false,
      })
      ..whenGet('$_base/d1/analysis', <String, dynamic>{
        'document_id': 'd1',
        'status': 'awaiting_confirmation',
        'support_level': 'fully_supported',
        'page_count': 2,
        'extracted_text_available': true,
        'document_type': '',
        'extractions': <dynamic>[
          <String, dynamic>{
            'id': 'e1',
            'document_id': 'd1',
            'field_key': 'amount',
            'value': '850000 TL',
            'page_number': 2,
            'confidence': 0.6,
            'verification_status': 'detected',
          },
        ],
      });

    await tester.pumpWidget(_host(client));
    await tester.pumpAndSettle();

    await tester.tap(find.text('sozlesme.txt'));
    await tester.pumpAndSettle();

    expect(find.text('850000 TL'), findsOneWidget);
    expect(find.text('Kaynak: sayfa 2'), findsOneWidget);
    expect(find.byIcon(Icons.check), findsOneWidget);
  });

  testWidgets('confirm extraction calls repository', (
    WidgetTester tester,
  ) async {
    final FakeApiClient client = FakeApiClient()
      ..whenGet(_base, <String, dynamic>{
        'items': <dynamic>[_doc(status: 'awaiting_confirmation')],
        'total': 1,
        'has_more': false,
      })
      ..whenGet('$_base/d1/analysis', <String, dynamic>{
        'document_id': 'd1',
        'status': 'awaiting_confirmation',
        'support_level': 'fully_supported',
        'page_count': 1,
        'extracted_text_available': true,
        'document_type': '',
        'extractions': <dynamic>[
          <String, dynamic>{
            'id': 'e1',
            'document_id': 'd1',
            'field_key': 'date',
            'value': '2023-06-12',
            'page_number': 1,
            'confidence': 0.6,
            'verification_status': 'detected',
          },
        ],
      })
      ..whenPost('$_base/d1/extractions/e1/confirm', <String, dynamic>{
        'id': 'e1',
        'document_id': 'd1',
        'verification_status': 'user_confirmed',
      });

    await tester.pumpWidget(_host(client));
    await tester.pumpAndSettle();
    await tester.tap(find.text('sozlesme.txt'));
    await tester.pumpAndSettle();

    await tester.tap(find.byIcon(Icons.check));
    await tester.pumpAndSettle();

    expect(client.postPaths, contains('$_base/d1/extractions/e1/confirm'));
  });
}
