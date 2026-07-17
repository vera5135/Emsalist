import 'download_service_unsupported.dart'
    if (dart.library.html) 'download_service_web.dart'
    if (dart.library.io) 'download_service_io.dart';

export 'download_service_unsupported.dart'
    if (dart.library.html) 'download_service_web.dart'
    if (dart.library.io) 'download_service_io.dart';

DownloadService getDownloadService() => createDownloadService();
