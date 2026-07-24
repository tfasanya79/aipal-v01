/// Web/iOS stub — background wake service is Android-only (C2).
class WakeBackgroundService {
  static Future<void> init() async {}

  static Future<bool> ensureRunning() async => false;

  static Future<void> stop() async {}

  static void setSuppressed(bool suppressed) {}

  static Future<bool> isRunning() async => false;
}
