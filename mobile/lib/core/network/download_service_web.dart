import 'dart:html' as html;

import 'download_service_unsupported.dart';

export 'download_service_unsupported.dart';

class WebDownloadService implements DownloadService {
  @override
  Future<void> saveAndOpen(DownloadedFile file) async {
    final html.Blob blob = html.Blob(<Object>[file.bytes], file.contentType);
    final String url = html.Url.createObjectUrl(blob);
    final html.AnchorElement anchor = html.AnchorElement(href: url)
      ..setAttribute('download', file.filename)
      ..style.display = 'none';
    html.document.body!.append(anchor);
    anchor.click();
    anchor.remove();
    html.Url.revokeObjectUrl(url);
  }
}

DownloadService createDownloadService() => WebDownloadService();
