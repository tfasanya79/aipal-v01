import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/app_state.dart';
import 'home_shell.dart';

const _ivory = Color(0xFFFAF9F5);
const _brandGreen = Color(0xFF003B2B);
const _teal = Color(0xFF003B2B);
const _ink = Color(0xFF211C24);

class LifeDashboardScreen extends StatefulWidget {
  const LifeDashboardScreen({super.key});

  @override
  State<LifeDashboardScreen> createState() => _LifeDashboardScreenState();
}

class _LifeDashboardScreenState extends State<LifeDashboardScreen> {
  Future<Map<String, dynamic>>? _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<Map<String, dynamic>> _load() async {
    return context.read<AppState>().api.getLivingDashboard();
  }

  @override
  Widget build(BuildContext context) {
    return AiPalShellScaffold(
      title: 'Life Dashboard',
      subtitle: 'A living overview of today, goals, mood, focus, and people',
      showDesktopSidebar: false,
      showMobileBottomNav: false,
      onNotificationsTap: () {},
      onProfileTap: () {},
      body: ColoredBox(
        color: _ivory,
        child: FutureBuilder<Map<String, dynamic>>(
          future: _future,
          builder: (context, snapshot) {
            if (snapshot.connectionState == ConnectionState.waiting) {
              return const Center(
                child: CircularProgressIndicator(color: _teal),
              );
            }
            if (snapshot.hasError) {
              return _CenteredMessage(
                title: 'Dashboard could not load',
                body: snapshot.error.toString(),
              );
            }
            final data = snapshot.data ?? const <String, dynamic>{};
            final today = data['today'] as Map<String, dynamic>? ?? const {};
            final nextUp = data['next_up'] as Map<String, dynamic>?;
            final mood = data['mood'] as Map<String, dynamic>? ?? const {};
            final focus = data['focus'] as Map<String, dynamic>? ?? const {};
            final goals = data['goals'] as List<dynamic>? ?? const [];
            final relationships =
                data['relationships'] as List<dynamic>? ?? const [];
            final habits = data['habits'] as List<dynamic>? ?? const [];
            final insights = data['insights'] as List<dynamic>? ?? const [];

            return RefreshIndicator(
              color: _teal,
              onRefresh: () async {
                final next = _load();
                setState(() => _future = next);
                await next;
              },
              child: ListView(
                padding: const EdgeInsets.fromLTRB(20, 24, 20, 96),
                children: [
                  _HeroPanel(
                    greeting: data['greeting']?.toString() ?? 'Good morning',
                    completion: today['completion_percent'] as int? ?? 0,
                    total: today['total'] as int? ?? 0,
                    nextTitle: nextUp?['title']?.toString(),
                  ),
                  const SizedBox(height: 16),
                  LayoutBuilder(
                    builder: (context, constraints) {
                      final twoColumns = constraints.maxWidth > 760;
                      final cards = [
                        _MetricCard(
                          label: 'Today',
                          value:
                              '${today['completed'] ?? 0}/${today['total'] ?? 0}',
                          detail: '${today['open'] ?? 0} open items',
                          icon: Icons.today_rounded,
                        ),
                        _MetricCard(
                          label: 'Mood',
                          value:
                              mood['trend']?.toString() ??
                              'Not enough signal yet',
                          detail: '${mood['signals'] ?? 0} recent signals',
                          icon: Icons.self_improvement_rounded,
                        ),
                        _MetricCard(
                          label: 'Focus',
                          value: '${focus['minutes_today'] ?? 0}m',
                          detail: '${focus['hours_today'] ?? 0} hours today',
                          icon: Icons.center_focus_strong_rounded,
                        ),
                        _MetricCard(
                          label: 'Next up',
                          value: nextUp?['title']?.toString() ?? 'Nothing next',
                          detail:
                              nextUp?['type']?.toString() ??
                              'Your day is clear for now',
                          icon: Icons.upcoming_rounded,
                        ),
                      ];
                      if (!twoColumns) {
                        return Column(
                          children: cards
                              .map(
                                (card) => Padding(
                                  padding: const EdgeInsets.only(bottom: 12),
                                  child: card,
                                ),
                              )
                              .toList(),
                        );
                      }
                      return Wrap(
                        spacing: 12,
                        runSpacing: 12,
                        children: cards
                            .map(
                              (card) => SizedBox(
                                width: (constraints.maxWidth - 12) / 2,
                                child: card,
                              ),
                            )
                            .toList(),
                      );
                    },
                  ),
                  const SizedBox(height: 16),
                  _SectionPanel(
                    title: 'Goals',
                    empty: 'No active goals yet.',
                    children: goals.map((goal) {
                      final row = goal as Map<String, dynamic>;
                      return _ProgressRow(
                        title: row['title']?.toString() ?? 'Untitled goal',
                        subtitle: row['life_area']?.toString() ?? 'Life goal',
                        progress: row['progress'] as int? ?? 0,
                      );
                    }).toList(),
                  ),
                  const SizedBox(height: 16),
                  _SectionPanel(
                    title: 'Relationships',
                    empty: 'No relationship signals yet.',
                    children: relationships.map((person) {
                      final row = person as Map<String, dynamic>;
                      return _SimpleRow(
                        icon: Icons.person_rounded,
                        title: row['name']?.toString() ?? 'Someone important',
                        subtitle:
                            row['description']?.toString() ??
                            row['type']?.toString() ??
                            'Person',
                      );
                    }).toList(),
                  ),
                  const SizedBox(height: 16),
                  _SectionPanel(
                    title: 'Habits',
                    empty: 'No active habits yet.',
                    children: habits.map((habit) {
                      final row = habit as Map<String, dynamic>;
                      return _SimpleRow(
                        icon: Icons.repeat_rounded,
                        title: row['name']?.toString() ?? 'Habit',
                        subtitle:
                            '${row['recent_logs'] ?? 0} logs · ${row['frequency'] ?? 'daily'}',
                      );
                    }).toList(),
                  ),
                  const SizedBox(height: 16),
                  _SectionPanel(
                    title: 'Grounded insights',
                    empty:
                        'AiPal will show insights here once there is enough real activity.',
                    children: insights
                        .map(
                          (insight) => _SimpleRow(
                            icon: Icons.insights_rounded,
                            title: insight.toString(),
                            subtitle: 'Based on current dashboard data',
                          ),
                        )
                        .toList(),
                  ),
                ],
              ),
            );
          },
        ),
      ),
    );
  }
}

class _HeroPanel extends StatelessWidget {
  const _HeroPanel({
    required this.greeting,
    required this.completion,
    required this.total,
    required this.nextTitle,
  });

  final String greeting;
  final int completion;
  final int total;
  final String? nextTitle;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(22),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [Colors.white, Color(0xFFEAF3EF)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(30),
        border: Border.all(color: Colors.white.withValues(alpha: 0.8)),
        boxShadow: [
          BoxShadow(
            color: _teal.withValues(alpha: 0.12),
            blurRadius: 30,
            offset: const Offset(0, 18),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            greeting,
            style: const TextStyle(
              color: _brandGreen,
              fontSize: 30,
              fontWeight: FontWeight.w800,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            total == 0
                ? 'Your dashboard is quiet. As you use AiPal, this becomes a living map of your day.'
                : 'Today is $completion% complete${nextTitle == null ? '.' : ', and next up is $nextTitle.'}',
            style: const TextStyle(color: _ink, fontSize: 16, height: 1.45),
          ),
        ],
      ),
    );
  }
}

class _MetricCard extends StatelessWidget {
  const _MetricCard({
    required this.label,
    required this.value,
    required this.detail,
    required this.icon,
  });

  final String label;
  final String value;
  final String detail;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return _GlassPanel(
      child: Row(
        children: [
          _IconBadge(icon),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label, style: const TextStyle(color: _teal)),
                const SizedBox(height: 4),
                Text(
                  value,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: _ink,
                    fontSize: 20,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                Text(detail, style: const TextStyle(color: Colors.black54)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _SectionPanel extends StatelessWidget {
  const _SectionPanel({
    required this.title,
    required this.empty,
    required this.children,
  });

  final String title;
  final String empty;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return _GlassPanel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: const TextStyle(
              color: _brandGreen,
              fontSize: 19,
              fontWeight: FontWeight.w800,
            ),
          ),
          const SizedBox(height: 12),
          if (children.isEmpty)
            Text(empty, style: const TextStyle(color: Colors.black54))
          else
            ...children,
        ],
      ),
    );
  }
}

class _ProgressRow extends StatelessWidget {
  const _ProgressRow({
    required this.title,
    required this.subtitle,
    required this.progress,
  });

  final String title;
  final String subtitle;
  final int progress;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  title,
                  style: const TextStyle(
                    color: _ink,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              Text('$progress%', style: const TextStyle(color: _teal)),
            ],
          ),
          const SizedBox(height: 6),
          ClipRRect(
            borderRadius: BorderRadius.circular(999),
            child: LinearProgressIndicator(
              value: progress.clamp(0, 100) / 100,
              minHeight: 8,
              color: _teal,
              backgroundColor: _teal.withValues(alpha: 0.12),
            ),
          ),
          const SizedBox(height: 5),
          Text(subtitle, style: const TextStyle(color: Colors.black54)),
        ],
      ),
    );
  }
}

class _SimpleRow extends StatelessWidget {
  const _SimpleRow({
    required this.icon,
    required this.title,
    required this.subtitle,
  });

  final IconData icon;
  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        children: [
          _IconBadge(icon),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    color: _ink,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                Text(
                  subtitle,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(color: Colors.black54),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _IconBadge extends StatelessWidget {
  const _IconBadge(this.icon);
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 42,
      height: 42,
      decoration: BoxDecoration(
        color: _teal.withValues(alpha: 0.11),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Icon(icon, color: _teal),
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
      color: Colors.white.withValues(alpha: 0.76),
      borderRadius: BorderRadius.circular(24),
      border: Border.all(color: Colors.white.withValues(alpha: 0.85)),
      boxShadow: [
        BoxShadow(
          color: _brandGreen.withValues(alpha: 0.06),
          blurRadius: 20,
          offset: const Offset(0, 12),
        ),
      ],
    ),
    child: child,
  );
}

class _CenteredMessage extends StatelessWidget {
  const _CenteredMessage({required this.title, required this.body});
  final String title;
  final String body;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              title,
              textAlign: TextAlign.center,
              style: const TextStyle(
                color: _brandGreen,
                fontSize: 22,
                fontWeight: FontWeight.w800,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              body,
              textAlign: TextAlign.center,
              style: const TextStyle(color: Colors.black54),
            ),
          ],
        ),
      ),
    );
  }
}
