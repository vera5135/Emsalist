import 'secure_session_store_base.dart'
    if (dart.library.html) 'secure_session_store_web.dart'
    if (dart.library.io) 'secure_session_store_io.dart';

export 'secure_session_store_base.dart'
    if (dart.library.html) 'secure_session_store_web.dart'
    if (dart.library.io) 'secure_session_store_io.dart';

SecureSessionStore createSecureSessionStore() => createStore();
