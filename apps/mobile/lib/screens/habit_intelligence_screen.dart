import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/app_state.dart';
import 'home_shell.dart';

const _brandGreen = Color(0xFF003B2B);
const _teal = Color(0xFF003B2B);

class HabitIntelligenceScreen extends StatefulWidget {
  const HabitIntelligenceScreen({super.key});

  @override
  State<HabitIntelligenceScreen> createState() =>
      _HabitIntelligenceScreenState();
}

class _HabitIntelligenceScreenState extends State<HabitIntelligenceScreen> {
  final _nameController = TextEditingController();
  final _lifeAreaController = TextEditingController();
  String _frequency = 'daily';
  Future<Map<String, dynamic>>? _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  @override
  void dispose() {
    _nameController.dispose();
    _lifeAreaController.dispose();
    super.dispose();
  }

  Future<Map<String, dynamic>> _load() async {
    final api = context.read<AppState>().api;
    final results = await Future.wait([
      api.listHabits(),
      api.getHabitSummary(),
    ]);
    return {
      'habits': results[0] as List<dynamic>,
      'summary': results[1] as Map<String, dynamic>,
    };
  }

  Future<void> _refresh() async {
    setState(() {
      _future = _load();
    });
  }

  Future<void> _create() async {
    final name = _nameController.text.trim();
    if (name.isEmpty) return;
    final api = context.read<AppState>().api;
    await api.createHabit({
      'name': name,
      if (_lifeAreaController.text.trim().isNotEmpty)
        'life_area': _lifeAreaController.text.trim(),
      'frequency': _frequency,
      'target_count': 1,
    });
    if (!mounted) return;
    _nameController.clear();
    setState(() {
      _future = _load();
    });
  }

  Future<void> _logHabit(String habitId) async {
    final api = context.read<AppState>().api;
    await api.logHabit(habitId, {'value': 1, 'source': 'manual'});
    if (!mounted) return;
    setState(() {
      _future = _load();
    });
  }

  @override
  Widget build(BuildContext context) {
    return AiPalShellScaffold(
      title: 'Habit Intelligence',
      subtitle: 'Track habits lightly and only when it helps',
      showDesktopSidebar: false,
      showMobileBottomNav: false,
      onNotificationsTap: () {},
      onProfileTap: () {},
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: FutureBuilder<Map<String, dynamic>>(
          future: _future,
          builder: (context, snapshot) {
            final habits =
                (snapshot.data?['habits'] as List<dynamic>? ?? const [])
                    .whereType<Map>()
                    .map((item) => item.cast<String, dynamic>())
                    .toList();
            final summary = snapshot.data?['summary'] as Map<String, dynamic>?;

            return ListView(
              padding: const EdgeInsets.fromLTRB(20, 24, 20, 96),
              children: [
                _GlassPanel(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'Habit intelligence',
                        style: TextStyle(
                          fontSize: 28,
                          fontWeight: FontWeight.w800,
                          color: _brandGreen,
                        ),
                      ),
                      const SizedBox(height: 8),
                      const Text(
                        'Add habits only when they matter. Keep it supportive, not noisy.',
                      ),
                      const SizedBox(height: 16),
                      TextField(
                        controller: _nameController,
                        decoration: const InputDecoration(
                          labelText: 'Habit name',
                        ),
                      ),
                      const SizedBox(height: 12),
                      TextField(
                        controller: _lifeAreaController,
                        decoration: const InputDecoration(
                          labelText: 'Life area (optional)',
                        ),
                      ),
                      const SizedBox(height: 12),
                      DropdownButtonFormField<String>(
                        initialValue: _frequency,
                        decoration: const InputDecoration(
                          labelText: 'Frequency',
                        ),
                        items: const [
                          DropdownMenuItem(
                            value: 'daily',
                            child: Text('Daily'),
                          ),
                          DropdownMenuItem(
                            value: 'weekly',
                            child: Text('Weekly'),
                          ),
                          DropdownMenuItem(
                            value: 'custom',
                            child: Text('Custom'),
                          ),
                        ],
                        onChanged: (value) =>
                            setState(() => _frequency = value ?? 'daily'),
                      ),
                      const SizedBox(height: 16),
                      Align(
                        alignment: Alignment.centerRight,
                        child: FilledButton(
                          style: FilledButton.styleFrom(
                            backgroundColor: _teal,
                            foregroundColor: Colors.white,
                          ),
                          onPressed: _create,
                          child: const Text('Create habit'),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 16),
                if (summary != null) ...[
                  _GlassPanel(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          'Summary',
                          style: TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w700,
                            color: _brandGreen,
                          ),
                        ),
                        const SizedBox(height: 8),
                        Text(summary['suggestions']?.toString() ?? ''),
                      ],
                    ),
                  ),
                  const SizedBox(height: 16),
                ],
                _GlassPanel(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'Tracked habits',
                        style: TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.w700,
                          color: _brandGreen,
                        ),
                      ),
                      const SizedBox(height: 12),
                      if (habits.isEmpty)
                        const Text('No habits yet.')
                      else
                        Column(
                          children: habits.map((habit) {
                            return Padding(
                              padding: const EdgeInsets.only(bottom: 10),
                              child: _HabitRow(
                                habit: habit,
                                onLog: () =>
                                    _logHabit(habit['id']?.toString() ?? ''),
                              ),
                            );
                          }).toList(),
                        ),
                    ],
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

class _GlassPanel extends StatelessWidget {
  const _GlassPanel({required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(18),
    decoration: BoxDecoration(
      color: Colors.white.withValues(alpha: 0.72),
      borderRadius: BorderRadius.circular(24),
      border: Border.all(color: Colors.white.withValues(alpha: 0.75)),
    ),
    child: child,
  );
}

class _HabitRow extends StatelessWidget {
  const _HabitRow({required this.habit, required this.onLog});
  final Map<String, dynamic> habit;
  final VoidCallback onLog;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFFFAF9F5),
        borderRadius: BorderRadius.circular(18),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  habit['name']?.toString() ?? '',
                  style: const TextStyle(
                    fontWeight: FontWeight.w700,
                    color: _brandGreen,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  '${habit['frequency']?.toString() ?? ''} · ${habit['life_area']?.toString() ?? 'general'}',
                ),
              ],
            ),
          ),
          TextButton(onPressed: onLog, child: const Text('Log')),
        ],
      ),
    );
  }
}
