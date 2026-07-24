import 'dart:io' show Platform;

import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:permission_handler/permission_handler.dart';

import 'wake_foreground_handler.dart';

/// Android foreground microphone service for background "Hi Pal" wake (C2).
class WakeBackgroundService {
  static const _serviceId = 258;

  static Future<void> init() async {
    if (!Platform.isAndroid) return;
    FlutterForegroundTask.init(
      androidNotificationOptions: AndroidNotificationOptions(
        channelId: 'aipal_wake',
        channelName: 'Hi Pal wake word',
        channelDescription:
            'AiPal listens for Hi Pal when enabled in Settings.',
        onlyAlertOnce: true,
        channelImportance: NotificationChannelImportance.LOW,
        priority: NotificationPriority.LOW,
      ),
      iosNotificationOptions: const IOSNotificationOptions(
        showNotification: false,
        playSound: false,
      ),
      foregroundTaskOptions: ForegroundTaskOptions(
        eventAction: ForegroundTaskEventAction.nothing(),
        autoRunOnBoot: false,
        autoRunOnMyPackageReplaced: false,
        allowWakeLock: true,
      ),
    );
  }

  static Future<bool> _ensureNotificationPermission() async {
    final status = await FlutterForegroundTask.checkNotificationPermission();
    if (status == NotificationPermission.granted) return true;
    final requested =
        await FlutterForegroundTask.requestNotificationPermission();
    return requested == NotificationPermission.granted;
  }

  static Future<bool> ensureRunning() async {
    if (!Platform.isAndroid) return false;
    final mic = await Permission.microphone.request();
    if (!mic.isGranted) return false;
    if (!await _ensureNotificationPermission()) return false;

    if (await FlutterForegroundTask.isRunningService) {
      return true;
    }

    final result = await FlutterForegroundTask.startService(
      serviceId: _serviceId,
      notificationTitle: 'AiPal is listening for Hi Pal',
      notificationText: 'Say Hi Pal to start Live hands-free',
      callback: startWakeCallback,
    );
    return result is ServiceRequestSuccess;
  }

  static Future<void> stop() async {
    if (!Platform.isAndroid) return;
    if (await FlutterForegroundTask.isRunningService) {
      await FlutterForegroundTask.stopService();
    }
  }

  static void setSuppressed(bool suppressed) {
    if (!Platform.isAndroid) return;
    FlutterForegroundTask.sendDataToTask({'suppress': suppressed});
  }

  static Future<bool> isRunning() async {
    if (!Platform.isAndroid) return false;
    return FlutterForegroundTask.isRunningService;
  }
}
