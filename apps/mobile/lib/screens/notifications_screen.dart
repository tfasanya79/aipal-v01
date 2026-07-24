import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/app_state.dart';
import '../services/web_title.dart';

class NotificationsScreen extends StatefulWidget {
  const NotificationsScreen({super.key});

  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends State<NotificationsScreen> {
  Future<List<Map<String, dynamic>>>? _notificationsFuture;
  Future<Map<String, dynamic>>? _preferencesFuture;
  String? _lastWebTitle;

  @override
  void initState() {
    super.initState();
    _notificationsFuture = _loadNotifications();
    _preferencesFuture = _loadPreferences();
  }

  Future<List<Map<String, dynamic>>> _loadNotifications() async {
    final rows = await context.read<AppState>().api.getNotifications();
    return rows.cast<Map<String, dynamic>>();
  }

  Future<Map<String, dynamic>> _loadPreferences() async {
    return context.read<AppState>().api.getNotificationPreferences();
  }

  Future<void> _refresh() async {
    await context.read<AppState>().refreshTodayView();
    if (!mounted) return;
    setState(() {
      _notificationsFuture = _loadNotifications();
      _preferencesFuture = _loadPreferences();
    });
  }

  Future<void> _markRead(String id) async {
    await context.read<AppState>().api.markNotificationRead(id);
    await _refresh();
  }

  Future<void> _dismiss(String id) async {
    await context.read<AppState>().api.dismissNotification(id);
    await _refresh();
  }

  Future<void> _updatePreference(String key, bool value) async {
    await context.read<AppState>().api.updateNotificationPreferences({
      key: value,
    });
    await _refresh();
  }

  String _timeLabel(String? raw) {
    if (raw == null || raw.isEmpty) return 'All day';
    try {
      final dt = DateTime.parse(raw).toLocal();
      final hour = dt.hour % 12 == 0 ? 12 : dt.hour % 12;
      final minute = dt.minute.toString().padLeft(2, '0');
      final period = dt.hour >= 12 ? 'PM' : 'AM';
      return '$hour:$minute $period';
    } catch (_) {
      return raw;
    }
  }

  void _syncWebTitle(String title) {
    if (!kIsWeb || _lastWebTitle == title) return;
    _lastWebTitle = title;
    setWebPageTitle(title);
  }

  @override
  Widget build(BuildContext context) {
    _syncWebTitle('Notifications · AiPal');
    return Scaffold(
      backgroundColor: const Color(0xFFFAF9F5),
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 34, 20, 24),
          children: [
            _SectionCard(
              title: 'Agenda notifications',
              subtitle:
                  'Reminders, meetings, task dues, and commitment follow-ups',
              child: FutureBuilder<List<Map<String, dynamic>>>(
                future: _notificationsFuture,
                builder: (context, snapshot) {
                  final rows = snapshot.data ?? const [];
                  if (snapshot.connectionState == ConnectionState.waiting) {
                    return const Padding(
                      padding: EdgeInsets.symmetric(vertical: 24),
                      child: Center(child: CircularProgressIndicator()),
                    );
                  }
                  if (rows.isEmpty) {
                    return const _EmptyNote(
                      text: 'No scheduled notifications yet.',
                    );
                  }
                  return Column(
                    children: rows
                        .map(
                          (row) => _NotificationRow(
                            icon: _iconFor(row['type']?.toString()),
                            title: row['title']?.toString() ?? 'Notification',
                            subtitle:
                                '${row['channel'] ?? 'in_app'} · ${row['status'] ?? 'pending'} · ${_timeLabel(row['scheduled_for']?.toString())}',
                            accent:
                                row['status'] == 'sent' ||
                                    row['status'] == 'read'
                                ? const Color(0xFF003B2B)
                                : const Color(0xFFFFC815),
                            onRead: () => _markRead(row['id'].toString()),
                            onDismiss: () => _dismiss(row['id'].toString()),
                          ),
                        )
                        .toList(),
                  );
                },
              ),
            ),
            const SizedBox(height: 18),
            _SectionCard(
              title: 'Notification preferences',
              subtitle: 'Choose how AiPal should nudge you',
              child: FutureBuilder<Map<String, dynamic>>(
                future: _preferencesFuture,
                builder: (context, snapshot) {
                  final prefs = snapshot.data ?? const <String, dynamic>{};
                  return Column(
                    children: [
                      _PreferenceToggle(
                        label: 'In-app notifications',
                        value: prefs['in_app_enabled'] as bool? ?? true,
                        onChanged: (value) =>
                            _updatePreference('in_app_enabled', value),
                      ),
                      const SizedBox(height: 10),
                      _PreferenceToggle(
                        label: 'Email reminders',
                        value: prefs['email_enabled'] as bool? ?? true,
                        onChanged: (value) =>
                            _updatePreference('email_enabled', value),
                      ),
                      const SizedBox(height: 10),
                      _PreferenceToggle(
                        label: 'Push notifications',
                        value: prefs['push_enabled'] as bool? ?? true,
                        onChanged: (value) =>
                            _updatePreference('push_enabled', value),
                      ),
                    ],
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }

  IconData _iconFor(String? type) {
    switch (type) {
      case 'meeting':
        return Icons.groups_rounded;
      case 'task_due':
        return Icons.task_alt_rounded;
      case 'commitment_followup':
      case 'smart_commitment_progress':
        return Icons.handshake_rounded;
      case 'smart_meeting_prep':
        return Icons.lightbulb_rounded;
      case 'smart_missed_followup':
        return Icons.volunteer_activism_rounded;
      case 'reminder':
        return Icons.notifications_active_rounded;
      default:
        return Icons.notifications_none_rounded;
    }
  }
}

class _SectionCard extends StatelessWidget {
  const _SectionCard({
    required this.title,
    required this.subtitle,
    required this.child,
  });

  final String title;
  final String subtitle;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.58),
        borderRadius: BorderRadius.circular(28),
        border: Border.all(color: Colors.white.withValues(alpha: 0.82)),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF1A1F2C).withValues(alpha: 0.04),
            blurRadius: 32,
            offset: const Offset(0, 16),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: const TextStyle(
              fontFamily: 'Manrope',
              fontSize: 22,
              fontWeight: FontWeight.w800,
              color: Color(0xFF1B1C1A),
            ),
          ),
          const SizedBox(height: 6),
          Text(
            subtitle,
            style: const TextStyle(
              fontSize: 13.5,
              height: 1.45,
              color: Color(0xFF4B444D),
            ),
          ),
          const SizedBox(height: 16),
          child,
        ],
      ),
    );
  }
}

class _NotificationRow extends StatelessWidget {
  const _NotificationRow({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.accent,
    required this.onRead,
    required this.onDismiss,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final Color accent;
  final VoidCallback onRead;
  final VoidCallback onDismiss;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFFFCFBF8),
        borderRadius: BorderRadius.circular(22),
        border: Border.all(color: const Color(0xFFE6E1D6)),
      ),
      child: Row(
        children: [
          Container(
            width: 42,
            height: 42,
            decoration: BoxDecoration(
              color: accent.withValues(alpha: 0.12),
              borderRadius: BorderRadius.circular(14),
            ),
            child: Icon(icon, color: accent, size: 21),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    fontSize: 15,
                    height: 1.3,
                    fontWeight: FontWeight.w800,
                    color: Color(0xFF1B1C1A),
                  ),
                ),
                const SizedBox(height: 5),
                Text(
                  subtitle,
                  style: const TextStyle(
                    fontSize: 12.5,
                    height: 1.45,
                    color: Color(0xFF4B444D),
                  ),
                ),
              ],
            ),
          ),
          IconButton(
            tooltip: 'Mark read',
            onPressed: onRead,
            icon: const Icon(Icons.done_rounded),
            color: const Color(0xFF003B2B),
          ),
          IconButton(
            tooltip: 'Dismiss',
            onPressed: onDismiss,
            icon: const Icon(Icons.close_rounded),
            color: const Color(0xFFFFC815),
          ),
        ],
      ),
    );
  }
}

class _PreferenceToggle extends StatelessWidget {
  const _PreferenceToggle({
    required this.label,
    required this.value,
    required this.onChanged,
  });

  final String label;
  final bool value;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: Text(
            label,
            style: const TextStyle(
              fontSize: 14,
              fontWeight: FontWeight.w800,
              color: Color(0xFF1B1C1A),
            ),
          ),
        ),
        Switch(
          value: value,
          activeThumbColor: const Color(0xFF003B2B),
          onChanged: onChanged,
        ),
      ],
    );
  }
}

class _EmptyNote extends StatelessWidget {
  const _EmptyNote({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: const Color(0xFFF8F7F3),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: const Color(0xFFE6E1D6)),
      ),
      child: Text(
        text,
        style: const TextStyle(
          fontSize: 13.5,
          height: 1.45,
          color: Color(0xFF4B444D),
        ),
      ),
    );
  }
}
