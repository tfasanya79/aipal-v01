import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:device_calendar/device_calendar.dart';

/// v2.1: Read-only device calendar import for planning context.
class CalendarService {
  final _plugin = DeviceCalendarPlugin();

  Future<List<Map<String, dynamic>>> fetchTodayEvents() async {
    if (kIsWeb) return [];

    try {
      final perm = await _plugin.hasPermissions();
      if (perm.isSuccess && !perm.data!) {
        final req = await _plugin.requestPermissions();
        if (!req.isSuccess || !req.data!) return [];
      }
      final cals = await _plugin.retrieveCalendars();
      if (!cals.isSuccess || cals.data == null) return [];
      final now = DateTime.now();
      final start = DateTime(now.year, now.month, now.day);
      final end = start.add(const Duration(days: 1));
      final out = <Map<String, dynamic>>[];
      for (final cal in cals.data!) {
        final events = await _plugin.retrieveEvents(
          cal.id,
          RetrieveEventsParams(startDate: start, endDate: end),
        );
        if (!events.isSuccess || events.data == null) continue;
        for (final e in events.data!) {
          out.add({
            'external_id': e.eventId ?? '${cal.id}-${e.title}',
            'title': e.title ?? 'Event',
            'starts_at': (e.start ?? start).toUtc().toIso8601String(),
            'ends_at': e.end?.toUtc().toIso8601String(),
          });
        }
      }
      return out;
    } on MissingPluginException {
      return [];
    }
  }
}
