import 'auth_storage_stub.dart' if (dart.library.html) 'auth_storage_web.dart';

abstract class AuthStorage {
  Future<String?> readToken();
  Future<void> writeToken(String token);
  Future<void> deleteToken();
}

AuthStorage createAuthStorage() => createAuthStorageImpl();
