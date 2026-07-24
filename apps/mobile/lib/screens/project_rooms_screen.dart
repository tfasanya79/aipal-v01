import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/app_state.dart';

class ProjectRoomsScreen extends StatefulWidget {
  const ProjectRoomsScreen({super.key});

  @override
  State<ProjectRoomsScreen> createState() => _ProjectRoomsScreenState();
}

class _ProjectRoomsScreenState extends State<ProjectRoomsScreen> {
  late Future<List<dynamic>> _future;
  Map<String, dynamic>? _summary;

  @override
  void initState() {
    super.initState();
    _future = context.read<AppState>().api.listProjectRooms();
  }

  Future<void> _reload() async {
    setState(() => _future = context.read<AppState>().api.listProjectRooms());
  }

  Future<void> _createRoom() async {
    final controller = TextEditingController();
    final name = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Create project room'),
        content: TextField(
          controller: controller,
          decoration: const InputDecoration(labelText: 'Project name'),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, controller.text),
            child: const Text('Create'),
          ),
        ],
      ),
    );
    controller.dispose();
    if (name == null || name.trim().isEmpty || !mounted) return;
    await context.read<AppState>().api.createProjectRoom({'name': name.trim()});
    await _reload();
  }

  Future<void> _openSummary(String id) async {
    final data = await context.read<AppState>().api.getProjectRoomSummary(id);
    if (mounted) setState(() => _summary = data);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFFAF9F5),
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        foregroundColor: const Color(0xFF1B1C1A),
        title: const Text('Project Rooms'),
        actions: [
          IconButton(
            onPressed: _createRoom,
            icon: const Icon(Icons.add_rounded),
          ),
        ],
      ),
      body: FutureBuilder<List<dynamic>>(
        future: _future,
        builder: (context, snapshot) {
          final rooms = (snapshot.data ?? [])
              .whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList();
          return ListView(
            padding: const EdgeInsets.fromLTRB(20, 18, 20, 44),
            children: [
              const Text(
                'Founder-friendly workspaces for goals, meetings, tasks, memories, risks, and progress.',
                style: TextStyle(
                  color: Color(0xFF4B444D),
                  fontSize: 16,
                  height: 1.5,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 18),
              if (_summary != null) _RoomSummary(summary: _summary!),
              if (snapshot.connectionState == ConnectionState.waiting)
                const Center(child: CircularProgressIndicator())
              else if (rooms.isEmpty)
                const _EmptyRoomCard()
              else
                ...rooms.map(
                  (room) => _RoomCard(
                    room: room,
                    onTap: () => _openSummary(room['id'].toString()),
                  ),
                ),
            ],
          );
        },
      ),
    );
  }
}

class _RoomCard extends StatelessWidget {
  const _RoomCard({required this.room, required this.onTap});

  final Map<String, dynamic> room;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 14),
      child: Material(
        color: Colors.white.withValues(alpha: 0.62),
        borderRadius: BorderRadius.circular(28),
        child: InkWell(
          borderRadius: BorderRadius.circular(28),
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.all(18),
            child: Row(
              children: [
                const Icon(
                  Icons.dashboard_customize_rounded,
                  color: Color(0xFFFFC815),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        room['name']?.toString() ?? 'Project',
                        style: const TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.w900,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        room['description']?.toString() ??
                            'Tap to open project summary.',
                        style: const TextStyle(color: Color(0xFF4B444D)),
                      ),
                    ],
                  ),
                ),
                const Icon(Icons.chevron_right_rounded),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _RoomSummary extends StatelessWidget {
  const _RoomSummary({required this.summary});

  final Map<String, dynamic> summary;

  @override
  Widget build(BuildContext context) {
    final room = (summary['room'] as Map?)?.cast<String, dynamic>() ?? {};
    return Container(
      margin: const EdgeInsets.only(bottom: 18),
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: const Color(0xFFE7F5F5).withValues(alpha: 0.64),
        borderRadius: BorderRadius.circular(28),
        border: Border.all(
          color: const Color(0xFF003B2B).withValues(alpha: 0.14),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            room['name']?.toString() ?? 'Room',
            style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w900),
          ),
          const SizedBox(height: 8),
          Text(
            summary['summary']?.toString() ?? '',
            style: const TextStyle(height: 1.5, fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 12),
          LinearProgressIndicator(
            value: ((summary['progress'] as int? ?? 0) / 100).clamp(0, 1),
            color: const Color(0xFF003B2B),
            backgroundColor: Colors.white.withValues(alpha: 0.72),
          ),
        ],
      ),
    );
  }
}

class _EmptyRoomCard extends StatelessWidget {
  const _EmptyRoomCard();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(22),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.62),
        borderRadius: BorderRadius.circular(28),
      ),
      child: const Text(
        'No project rooms yet. Create Qring, CampusCart, FitAccess, AiPal, or Sammya when you are ready.',
      ),
    );
  }
}
