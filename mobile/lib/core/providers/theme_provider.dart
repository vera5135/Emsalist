import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../constants/app_constants.dart';

class ThemeModeNotifier extends StateNotifier<ThemeMode> {
  ThemeModeNotifier() : super(ThemeMode.system) {
    _load();
  }

  Future<void> _load() async {
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    final String? value = prefs.getString(AppConstants.prefThemeMode);
    state = _fromString(value);
  }

  Future<void> setThemeMode(ThemeMode mode) async {
    state = mode;
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    await prefs.setString(AppConstants.prefThemeMode, mode.name);
  }

  ThemeMode _fromString(String? value) {
    switch (value) {
      case 'light':
        return ThemeMode.light;
      case 'dark':
        return ThemeMode.dark;
      default:
        return ThemeMode.system;
    }
  }
}

final StateNotifierProvider<ThemeModeNotifier, ThemeMode> themeModeProvider =
    StateNotifierProvider<ThemeModeNotifier, ThemeMode>(
      (Ref ref) => ThemeModeNotifier(),
    );
