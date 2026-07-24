import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:timezone/data/latest.dart' as tz;
import 'package:timezone/timezone.dart' as tz;

typedef NudgeForegroundCallback = void Function(int taskId, int minutes);

class NotificationService {
  NotificationService._();
  static final instance = NotificationService._();

  final _plugin = FlutterLocalNotificationsPlugin();
  static const morningId = 1;
  static const eveningId = 2;
  static const _taskNudgeBaseId = 10000;
  static const nudgeLeadMinutes = 12;
  static const maxNudgesPerDay = 8;

  NudgeForegroundCallback? onForegroundNudge;

  Future<void> init({NudgeForegroundCallback? onForegroundNudge}) async {
    this.onForegroundNudge = onForegroundNudge;
    tz.initializeTimeZones();
    const android = AndroidInitializationSettings('@mipmap/ic_launcher');
    const ios = DarwinInitializationSettings();
    await _plugin.initialize(
      const InitializationSettings(android: android, iOS: ios),
      onDidReceiveNotificationResponse: _onNotificationResponse,
    );
  }

  void _onNotificationResponse(NotificationResponse response) {
    final payload = response.payload;
    if (payload == null || !payload.startsWith('nudge:')) return;
    final parts = payload.split(':');
    if (parts.length < 3) return;
    final taskId = int.tryParse(parts[1]);
    final minutes = int.tryParse(parts[2]);
    if (taskId != null && minutes != null) {
      onForegroundNudge?.call(taskId, minutes);
    }
  }

  Future<void> scheduleMorningBrief({
    required int hour,
    required int minute,
  }) async {
    await _plugin.zonedSchedule(
      morningId,
      'Good morning',
      'What should we plan for today?',
      _nextInstance(hour, minute),
      const NotificationDetails(
        android: AndroidNotificationDetails('aipal_daily', 'Daily briefs'),
        iOS: DarwinNotificationDetails(),
      ),
      androidScheduleMode: AndroidScheduleMode.inexactAllowWhileIdle,
      uiLocalNotificationDateInterpretation:
          UILocalNotificationDateInterpretation.absoluteTime,
      matchDateTimeComponents: DateTimeComponents.time,
    );
  }

  Future<void> scheduleEveningRecap({
    required int hour,
    required int minute,
  }) async {
    await _plugin.zonedSchedule(
      eveningId,
      'Evening recap',
      'How did today go?',
      _nextInstance(hour, minute),
      const NotificationDetails(
        android: AndroidNotificationDetails('aipal_daily', 'Daily briefs'),
        iOS: DarwinNotificationDetails(),
      ),
      androidScheduleMode: AndroidScheduleMode.inexactAllowWhileIdle,
      uiLocalNotificationDateInterpretation:
          UILocalNotificationDateInterpretation.absoluteTime,
      matchDateTimeComponents: DateTimeComponents.time,
    );
  }

  /// Schedule up to [maxNudgesPerDay] task reminders [nudgeLeadMinutes] before due_at.
  Future<void> rescheduleTaskNudges({
    required List<Map<String, dynamic>> tasks,
    required String wakeName,
  }) async {
    for (var i = 0; i < 200; i++) {
      await _plugin.cancel(_taskNudgeBaseId + i);
    }

    final now = tz.TZDateTime.now(tz.local);
    var scheduled = 0;
    final open = tasks.where((t) {
      final status = t['status'] as String? ?? 'planned';
      return status == 'planned' ||
          status == 'in_progress' ||
          status == 'deferred';
    }).toList();

    open.sort((a, b) {
      final ad = a['due_at'] as String?;
      final bd = b['due_at'] as String?;
      if (ad == null && bd == null) return 0;
      if (ad == null) return 1;
      if (bd == null) return -1;
      return ad.compareTo(bd);
    });

    for (final task in open) {
      if (scheduled >= maxNudgesPerDay) break;
      final dueRaw = task['due_at'] as String?;
      final id = task['id'] as int?;
      final title = task['title'] as String? ?? 'task';
      if (dueRaw == null || id == null) continue;

      DateTime dueLocal;
      try {
        dueLocal = DateTime.parse(dueRaw).toLocal();
      } catch (_) {
        continue;
      }

      final fireAt = tz.TZDateTime.from(
        dueLocal.subtract(const Duration(minutes: nudgeLeadMinutes)),
        tz.local,
      );
      if (fireAt.isBefore(now)) continue;

      final hour = dueLocal.hour;
      if (hour >= 22 || hour < 7) continue;

      final notifId = _taskNudgeBaseId + (id % 200);
      await _plugin.zonedSchedule(
        notifId,
        'AiPal',
        'Hi $wakeName, $nudgeLeadMinutes min to $title',
        fireAt,
        NotificationDetails(
          android: const AndroidNotificationDetails(
            'aipal_nudges',
            'Task reminders',
            channelDescription: 'Reminders before scheduled tasks',
          ),
          iOS: DarwinNotificationDetails(
            presentAlert: true,
            presentSound: true,
            subtitle: title,
          ),
        ),
        androidScheduleMode: AndroidScheduleMode.inexactAllowWhileIdle,
        uiLocalNotificationDateInterpretation:
            UILocalNotificationDateInterpretation.absoluteTime,
        payload: 'nudge:$id:$nudgeLeadMinutes',
      );
      scheduled++;
    }
  }

  tz.TZDateTime _nextInstance(int hour, int minute) {
    final now = tz.TZDateTime.now(tz.local);
    var scheduled = tz.TZDateTime(
      tz.local,
      now.year,
      now.month,
      now.day,
      hour,
      minute,
    );
    if (scheduled.isBefore(now)) {
      scheduled = scheduled.add(const Duration(days: 1));
    }
    return scheduled;
  }
}
