import 'dart:io' show Platform;

bool systemPlatformIsAndroid() {
  try {
    return Platform.isAndroid;
  } on Object {
    return false;
  }
}
