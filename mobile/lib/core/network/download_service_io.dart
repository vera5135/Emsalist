import 'dart:io' as io;

import 'package:open_filex/open_filex.dart';
import 'package:path_provider/path_provider.dart';

import 'download_service_unsupported.dart';

export 'download_service_unsupported.dart';

class IoDownloadService implements DownloadService {
  @override
  Future<void> saveAndOpen(DownloadedFile file) async {
    final io.Directory dir = await getTemporaryDirectory();
    final String filePath = '${dir.path}/${file.filename}';
    final io.File f = io.File(filePath);
    await f.writeAsBytes(file.bytes);
    await OpenFilex.open(filePath, type: file.contentType);
  }
}

DownloadService createDownloadService() => IoDownloadService();
