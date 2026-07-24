import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/app_state.dart';
import 'home_shell.dart';

const _brandGreen = Color(0xFF003B2B);
const _teal = Color(0xFF003B2B);

class AccountabilityScreen extends StatefulWidget {
  const AccountabilityScreen({super.key});

  @override
  State<AccountabilityScreen> createState() => _AccountabilityScreenState();
}

class _AccountabilityScreenState extends State<AccountabilityScreen> {
  Future<Map<String, dynamic>>? _future;
  Map<String, dynamic>? _snapshot;
  Map<String, dynamic>? _comparison;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<Map<String, dynamic>> _load() async {
    final api = context.read<AppState>().api;
    final latest = await api.getLatestAccountabilitySnapshot();
    return latest;
  }

  Future<void> _refresh() async {
    setState(() {
      _future = _load();
    });
  }

  Future<void> _generate() async {
    final api = context.read<AppState>().api;
    final now = DateTime.now();
    final start = now
        .subtract(const Duration(days: 6))
        .toIso8601String()
        .split('T')
        .first;
    final end = now.toIso8601String().split('T').first;
    final snapshot = await api.createAccountabilitySnapshot(
      periodStart: start,
      periodEnd: end,
    );
    if (!mounted) return;
    setState(() {
      _snapshot = snapshot;
      _future = _load();
    });
  }

  Future<void> _compare() async {
    final api = context.read<AppState>().api;
    final now = DateTime.now();
    final currentStart = now.subtract(const Duration(days: 6));
    final currentEnd = now;
    final previousEnd = currentStart.subtract(const Duration(days: 1));
    final previousStart = previousEnd.subtract(const Duration(days: 6));
    final result = await api.compareAccountability({
      'previous_period_start': previousStart.toIso8601String().split('T').first,
      'previous_period_end': previousEnd.toIso8601String().split('T').first,
      'current_period_start': currentStart.toIso8601String().split('T').first,
      'current_period_end': currentEnd.toIso8601String().split('T').first,
    });
    if (!mounted) return;
    setState(() {
      _comparison = result;
    });
  }

  @override
  Widget build(BuildContext context) {
    return AiPalShellScaffold(
      title: 'Accountability',
      subtitle: 'See what moved, what stalled, and what got in the way',
      showDesktopSidebar: false,
      showMobileBottomNav: false,
      onNotificationsTap: () {},
      onProfileTap: () {},
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: FutureBuilder<Map<String, dynamic>>(
          future: _future,
          builder: (context, snapshot) {
            final latest = snapshot.data;
            return ListView(
              padding: const EdgeInsets.fromLTRB(20, 24, 20, 96),
              children: [
                _GlassPanel(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'Weekly accountability',
                        style: TextStyle(
                          fontSize: 28,
                          fontWeight: FontWeight.w800,
                          color: _brandGreen,
                        ),
                      ),
                      const SizedBox(height: 8),
                      const Text(
                        'A lightweight check on progress, habits, blockers, and your next accountability question.',
                      ),
                      const SizedBox(height: 16),
                      Wrap(
                        spacing: 12,
                        runSpacing: 12,
                        children: [
                          FilledButton(
                            style: FilledButton.styleFrom(
                              backgroundColor: _teal,
                              foregroundColor: Colors.white,
                            ),
                            onPressed: _generate,
                            child: const Text('Generate snapshot'),
                          ),
                          OutlinedButton(
                            onPressed: _compare,
                            child: const Text('Compare periods'),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 16),
                if (_snapshot != null) _SnapshotCard(snapshotData: _snapshot!),
                if (_comparison != null) ...[
                  const SizedBox(height: 16),
                  _GlassPanel(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          'Comparison',
                          style: TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w700,
                            color: _brandGreen,
                          ),
                        ),
                        const SizedBox(height: 8),
                        Text(
                          _comparison!['accountability_question']?.toString() ??
                              '',
                        ),
                        const SizedBox(height: 8),
                        Text(_comparison.toString()),
                      ],
                    ),
                  ),
                ],
                if (latest != null) ...[
                  const SizedBox(height: 16),
                  _SnapshotCard(snapshotData: latest),
                ],
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

class _SnapshotCard extends StatelessWidget {
  const _SnapshotCard({required this.snapshotData});
  final Map<String, dynamic> snapshotData;

  @override
  Widget build(BuildContext context) {
    return _GlassPanel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Latest snapshot',
            style: TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.w700,
              color: _brandGreen,
            ),
          ),
          const SizedBox(height: 8),
          Text(snapshotData['reflection']?.toString() ?? 'No reflection yet.'),
          const SizedBox(height: 8),
          Text(
            'Score: ${snapshotData['score']?.toString() ?? '—'}',
            style: const TextStyle(color: _teal),
          ),
          const SizedBox(height: 8),
          Text('Tasks: ${snapshotData['tasks_summary']?.toString() ?? ''}'),
          const SizedBox(height: 8),
          Text('Habits: ${snapshotData['habits_summary']?.toString() ?? ''}'),
        ],
      ),
    );
  }
}
