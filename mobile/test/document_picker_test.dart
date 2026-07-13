import 'dart:typed_data';

import 'package:emsalist_mobile/core/constants/app_constants.dart';
import 'package:emsalist_mobile/features/documents/data/document_picker.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('accepts an approved document and assigns its MIME type', () {
    final PickedDocument document = validatePickedDocument(
      bytes: Uint8List.fromList(<int>[1, 2, 3]),
      filename: 'dilekce.PDF',
      extension: 'PDF',
    );

    expect(document.filename, 'dilekce.PDF');
    expect(document.mimeType, 'application/pdf');
  });

  test('rejects an unsupported document type', () {
    expect(
      () => validatePickedDocument(
        bytes: Uint8List.fromList(<int>[1]),
        filename: 'archive.exe',
        extension: 'exe',
      ),
      throwsA(isA<DocumentPickerException>()),
    );
  });

  test('rejects an empty document', () {
    expect(
      () => validatePickedDocument(
        bytes: Uint8List(0),
        filename: 'empty.txt',
        extension: 'txt',
      ),
      throwsA(isA<DocumentPickerException>()),
    );
  });

  test('rejects a document larger than 15 MB', () {
    expect(
      () => validatePickedDocument(
        bytes: Uint8List(AppConstants.maxUploadSizeBytes + 1),
        filename: 'large.pdf',
        extension: 'pdf',
      ),
      throwsA(isA<DocumentPickerException>()),
    );
  });
}
