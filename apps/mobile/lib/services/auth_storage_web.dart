// ignore_for_file: avoid_web_libraries_in_flutter, deprecated_member_use

import 'dart:html' as html;

import 'auth_storage.dart';

class _WebAuthStorage implements AuthStorage {
  static const _key = 'aipal.auth.token';

  @override
  Future<void> deleteToken() async {
    html.window.localStorage.remove(_key);
  }

  @override
  Future<String?> readToken() async {
    return html.window.localStorage[_key];
  }

  @override
  Future<void> writeToken(String token) async {
    html.window.localStorage[_key] = token;
  }
}

AuthStorage createAuthStorageImpl() => _WebAuthStorage();
