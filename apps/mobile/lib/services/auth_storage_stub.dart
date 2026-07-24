import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'auth_storage.dart';

class _SecureAuthStorage implements AuthStorage {
  static const _key = 'token';
  static const _storage = FlutterSecureStorage();

  @override
  Future<void> deleteToken() => _storage.delete(key: _key);

  @override
  Future<String?> readToken() => _storage.read(key: _key);

  @override
  Future<void> writeToken(String token) =>
      _storage.write(key: _key, value: token);
}

AuthStorage createAuthStorageImpl() => _SecureAuthStorage();
