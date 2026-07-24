import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Client-side prefs for wake word (default off until user opts in).
class WakeWordPrefs {
  static const _enabledKey = 'wake_word_enabled';
  static const _introKey = 'wake_word_intro_shown';
  static const _storage = FlutterSecureStorage();

  static Future<bool> isEnabled() async {
    final v = await _storage.read(key: _enabledKey);
    return v == 'true';
  }

  static Future<void> setEnabled(bool value) async {
    await _storage.write(key: _enabledKey, value: value ? 'true' : 'false');
  }

  static Future<bool> introShown() async {
    final v = await _storage.read(key: _introKey);
    return v == 'true';
  }

  static Future<void> markIntroShown() async {
    await _storage.write(key: _introKey, value: 'true');
  }
}
