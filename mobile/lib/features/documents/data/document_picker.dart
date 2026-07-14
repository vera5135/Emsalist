import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';

import '../../../core/constants/app_constants.dart';

class PickedDocument {
  const PickedDocument({
    required this.bytes,
    required this.filename,
    this.mimeType,
  });

  final Uint8List bytes;
  final String filename;
  final String? mimeType;
}

class DocumentPickerException implements Exception {
  const DocumentPickerException(this.message);

  final String message;
}

abstract interface class DocumentPicker {
  Future<PickedDocument?> pickDocument();
}

/// Opens the operating system's native file picker and returns upload-ready
/// bytes. Keeping this behind an interface makes widget tests independent from
/// platform channels.
class NativeDocumentPicker implements DocumentPicker {
  const NativeDocumentPicker();

  static const List<String> allowedExtensions = <String>[
    'pdf',
    'txt',
    'docx',
    'udf',
    'jpg',
    'jpeg',
    'png',
  ];

  @override
  Future<PickedDocument?> pickDocument() async {
    final FilePickerResult? result = await FilePicker.pickFiles(
      dialogTitle: 'Emsalist belgesi seçin',
      type: FileType.custom,
      allowedExtensions: allowedExtensions,
      allowMultiple: false,
      withData: true,
    );
    if (result == null) {
      return null;
    }

    final PlatformFile file = result.files.single;
    return validatePickedDocument(
      bytes: file.bytes,
      filename: file.name,
      extension: file.extension,
    );
  }
}

PickedDocument validatePickedDocument({
  required Uint8List? bytes,
  required String filename,
  required String? extension,
}) {
  final String normalizedExtension = (extension ?? filename.split('.').last)
      .toLowerCase();
  if (!NativeDocumentPicker.allowedExtensions.contains(normalizedExtension)) {
    throw const DocumentPickerException('Bu dosya türü desteklenmiyor.');
  }
  if (bytes == null) {
    throw const DocumentPickerException(
      'Seçilen dosya okunamadı. Lütfen tekrar deneyin.',
    );
  }
  if (bytes.isEmpty) {
    throw const DocumentPickerException('Boş dosyalar yüklenemez.');
  }
  if (bytes.length > AppConstants.maxUploadSizeBytes) {
    throw const DocumentPickerException('Belge 15 MB sınırını aşıyor.');
  }

  return PickedDocument(
    bytes: bytes,
    filename: filename,
    mimeType: _mimeTypeFor(normalizedExtension),
  );
}

String? _mimeTypeFor(String extension) {
  switch (extension) {
    case 'pdf':
      return 'application/pdf';
    case 'txt':
      return 'text/plain';
    case 'docx':
      return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
    case 'udf':
      return 'application/octet-stream';
    case 'jpg':
    case 'jpeg':
      return 'image/jpeg';
    case 'png':
      return 'image/png';
    default:
      return null;
  }
}
