class AppConstants {
  const AppConstants._();

  static const String appName = 'Emsalist';

  static const String bundleIdDev = 'com.emsalist.app.dev';
  static const String bundleIdStaging = 'com.emsalist.app.staging';
  static const String bundleIdProd = 'com.emsalist.app';

  static const String defaultCaseId = 'case-001';
  static const List<String> sampleCaseIds = <String>[
    'case-001',
    'case-002',
    'case-003',
  ];

  static const List<String> uyapStatusValues = <String>[
    'connected',
    'disconnected',
    'connecting',
    'error',
  ];

  static const String prefThemeMode = 'pref_theme_mode';

  static const double spacingXs = 4;
  static const double spacingSm = 8;
  static const double spacingMd = 16;
  static const double spacingLg = 24;
  static const double spacingXl = 32;

  static const double radiusSm = 8;
  static const double radiusMd = 12;
  static const double radiusLg = 16;
}
