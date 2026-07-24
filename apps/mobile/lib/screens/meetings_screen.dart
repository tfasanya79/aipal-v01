import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/app_state.dart';

class MeetingsScreen extends StatefulWidget {
  const MeetingsScreen({super.key});

  @override
  State<MeetingsScreen> createState() => _MeetingsScreenState();
}

class _MeetingsScreenState extends State<MeetingsScreen> {
  late Future<List<dynamic>> _future;
  String? _brief;
  String? _summary;

  @override
  void initState() {
    super.initState();
    _future = context.read<AppState>().api.getMeetings(upcoming: true);
  }

  Future<void> _refresh() async {
    setState(() {
      _future = context.read<AppState>().api.getMeetings(upcoming: true);
    });
  }

  Future<void> _briefMeeting(String id) async {
    final data = await context.read<AppState>().api.getMeetingBrief(id);
    if (mounted) setState(() => _brief = data['brief']?.toString());
  }

  Future<void> _addNotes(String id) async {
    final controller = TextEditingController();
    final content = await showModalBottomSheet<String>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _NotesSheet(controller: controller),
    );
    controller.dispose();
    if (content == null || content.trim().isEmpty || !mounted) return;
    final result = await context.read<AppState>().api.addMeetingNotes(
      id,
      content.trim(),
    );
    if (mounted) setState(() => _summary = result['summary']?.toString());
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFFAF9F5),
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        foregroundColor: const Color(0xFF1B1C1A),
        title: const Text('Meeting Assistant'),
      ),
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: FutureBuilder<List<dynamic>>(
          future: _future,
          builder: (context, snapshot) {
            final meetings = (snapshot.data ?? [])
                .whereType<Map>()
                .map((item) => item.cast<String, dynamic>())
                .toList();
            return ListView(
              padding: const EdgeInsets.fromLTRB(20, 18, 20, 44),
              children: [
                const Text(
                  'Prepare before meetings, capture notes after, and turn follow-ups into clear next steps.',
                  style: TextStyle(
                    color: Color(0xFF4B444D),
                    fontSize: 16,
                    height: 1.5,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 18),
                if (_brief != null)
                  _InsightCard(title: 'Preparation brief', text: _brief!),
                if (_summary != null)
                  _InsightCard(title: 'Latest summary', text: _summary!),
                if (snapshot.connectionState == ConnectionState.waiting)
                  const Center(child: CircularProgressIndicator())
                else if (meetings.isEmpty)
                  const _MeetingEmpty()
                else
                  ...meetings.map(
                    (meeting) => _MeetingCard(
                      meeting: meeting,
                      onBrief: () => _briefMeeting(meeting['id'].toString()),
                      onNotes: () => _addNotes(meeting['id'].toString()),
                    ),
                  ),
              ],
            );
          },
        ),
      ),
    );
  }
}

class _MeetingCard extends StatelessWidget {
  const _MeetingCard({
    required this.meeting,
    required this.onBrief,
    required this.onNotes,
  });

  final Map<String, dynamic> meeting;
  final VoidCallback onBrief;
  final VoidCallback onNotes;

  @override
  Widget build(BuildContext context) {
    final title = meeting['title']?.toString() ?? 'Meeting';
    final time = _formatMeetingTime(meeting['start_time']?.toString());
    final participants = meeting['participants']?.toString();
    return Container(
      margin: const EdgeInsets.only(bottom: 14),
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.62),
        borderRadius: BorderRadius.circular(28),
        border: Border.all(color: Colors.white.withValues(alpha: 0.9)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.groups_rounded, color: Color(0xFF003B2B)),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  title,
                  style: const TextStyle(
                    color: Color(0xFF1B1C1A),
                    fontSize: 18,
                    height: 1.25,
                    fontWeight: FontWeight.w900,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Text(
            participants == null ? time : '$time · $participants',
            style: const TextStyle(
              color: Color(0xFF4B444D),
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 14),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: [
              FilledButton.icon(
                onPressed: onBrief,
                icon: const Icon(Icons.auto_awesome_rounded),
                label: const Text('Prepare'),
                style: FilledButton.styleFrom(
                  backgroundColor: const Color(0xFFFFC815),
                  foregroundColor: Colors.white,
                ),
              ),
              OutlinedButton.icon(
                onPressed: onNotes,
                icon: const Icon(Icons.note_add_rounded),
                label: const Text('Add notes'),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _InsightCard extends StatelessWidget {
  const _InsightCard({required this.title, required this.text});

  final String title;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 14),
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: const Color(0xFFE7F5F5).withValues(alpha: 0.62),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(
          color: const Color(0xFF003B2B).withValues(alpha: 0.14),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: const TextStyle(
              color: Color(0xFF003B2B),
              fontWeight: FontWeight.w900,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            text,
            style: const TextStyle(
              color: Color(0xFF1B1C1A),
              height: 1.5,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }
}

class _MeetingEmpty extends StatelessWidget {
  const _MeetingEmpty();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(22),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.56),
        borderRadius: BorderRadius.circular(28),
        border: Border.all(color: Colors.white.withValues(alpha: 0.9)),
      ),
      child: const Text(
        'No upcoming meetings yet. When you schedule one, it will appear here and on Today.',
        style: TextStyle(
          color: Color(0xFF4B444D),
          height: 1.5,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}

class _NotesSheet extends StatelessWidget {
  const _NotesSheet({required this.controller});

  final TextEditingController controller;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        bottom: MediaQuery.of(context).viewInsets.bottom,
      ),
      child: Container(
        padding: const EdgeInsets.all(22),
        decoration: const BoxDecoration(
          color: Color(0xFFFAF9F5),
          borderRadius: BorderRadius.vertical(top: Radius.circular(30)),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: controller,
              minLines: 5,
              maxLines: 9,
              decoration: const InputDecoration(
                labelText: 'Meeting notes',
                hintText: 'Decisions, action items, follow-ups...',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 14),
            FilledButton(
              onPressed: () => Navigator.pop(context, controller.text),
              child: const Text('Save notes'),
            ),
          ],
        ),
      ),
    );
  }
}

String _formatMeetingTime(String? value) {
  if (value == null) return 'Time not set';
  final parsed = DateTime.tryParse(value)?.toLocal();
  if (parsed == null) return value;
  final hour = parsed.hour == 0
      ? 12
      : parsed.hour > 12
      ? parsed.hour - 12
      : parsed.hour;
  final minute = parsed.minute.toString().padLeft(2, '0');
  final suffix = parsed.hour >= 12 ? 'PM' : 'AM';
  return '$hour:$minute $suffix';
}
