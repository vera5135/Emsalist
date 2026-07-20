import 'dart:typed_data';

class DownloadedFile {
  const DownloadedFile({
    required this.bytes,
    required this.filename,
    required this.contentType,
  });

  final Uint8List bytes;
  final String filename;
  final String contentType;
}

abstract class DownloadService {
  Future<void> saveAndOpen(DownloadedFile file);
}

DownloadService createDownloadService() => _UnsupportedDownloadService();

class _UnsupportedDownloadService implements DownloadService {
  @override
  Future<void> saveAndOpen(DownloadedFile file) {
    throw UnsupportedError(
      'DownloadService is not supported on this platform.',
    );
  }
}
