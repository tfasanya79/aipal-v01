import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/app_state.dart';
import 'home_shell.dart';

const Color _timelineDotColor = Color(0xFF003B2B);

class InsightsScreen extends StatefulWidget {
  const InsightsScreen({super.key});

  @override
  State<InsightsScreen> createState() => _InsightsScreenState();
}

class _InsightsScreenState extends State<InsightsScreen> {
  Future<Map<String, dynamic>>? _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<Map<String, dynamic>> _load() async {
    final api = context.read<AppState>().api;
    final results = await Future.wait([
      api.listGoals(),
      api.listReflections(),
      api.listMemories(),
      api.listConversationSessions(),
      api.taskSummary(),
      api.getLifeAreaInsights(),
      api.getCompanionScore(),
      api.getLatestWeeklyReview(),
      api.getDueFollowups(),
      api.getMemoryTimeline(limit: 24),
      api.getWeeklyInsights(),
      api.getMonthlyInsights(),
      api.getDeepLifeAreaInsights(),
    ]);
    return {
      'goals': results[0] as List<dynamic>,
      'reflections': results[1] as List<dynamic>,
      'memories': results[2] as List<dynamic>,
      'sessions': results[3] as List<dynamic>,
      'taskSummary': results[4] as Map<String, dynamic>,
      'lifeAreas': results[5] as Map<String, dynamic>,
      'companionScore': results[6] as Map<String, dynamic>,
      'weeklyReview': results[7] as Map<String, dynamic>?,
      'followups': results[8] as List<dynamic>,
      'timeline': results[9] as List<dynamic>,
      'weeklyInsights': results[10] as Map<String, dynamic>,
      'monthlyInsights': results[11] as Map<String, dynamic>,
      'deepLifeAreas': results[12] as Map<String, dynamic>,
    };
  }

  Future<void> _refresh() async {
    setState(() {
      _future = _load();
    });
  }

  Map<String, int> _countByString(Iterable<dynamic> items, String key) {
    final out = <String, int>{};
    for (final item in items) {
      final value = item is Map ? item[key]?.toString().trim() : null;
      if (value == null || value.isEmpty) continue;
      out[value] = (out[value] ?? 0) + 1;
    }
    return out;
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();

    return AiPalShellScaffold(
      title: 'Insights',
      subtitle: 'Patterns, progress, and recent themes',
      showDesktopSidebar: false,
      showMobileBottomNav: false,
      onNotificationsTap: () {
        Navigator.of(context).pop();
        context.read<AppState>().goToTab(2);
      },
      onProfileTap: () {
        Navigator.of(context).pop();
        context.read<AppState>().goToTab(3);
      },
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: FutureBuilder<Map<String, dynamic>>(
          future: _future,
          builder: (context, snapshot) {
            final data = snapshot.data;
            final goals = (data?['goals'] as List<dynamic>? ?? const []);
            final reflections =
                (data?['reflections'] as List<dynamic>? ?? const []);
            final memories = (data?['memories'] as List<dynamic>? ?? const []);
            final sessions = (data?['sessions'] as List<dynamic>? ?? const []);
            final goalCounts = _countByString(goals, 'status');
            final moodCounts = _countByString(reflections, 'mood');
            final memoryTypeCounts = _countByString(memories, 'type');
            final weeklyReview = data?['weeklyReview'] as Map<String, dynamic>?;
            final weeklyInsights =
                data?['weeklyInsights'] as Map<String, dynamic>?;
            final monthlyInsights =
                data?['monthlyInsights'] as Map<String, dynamic>?;
            final deepLifeAreas =
                data?['deepLifeAreas'] as Map<String, dynamic>?;
            final followups = (data?['followups'] as List<dynamic>? ?? const [])
                .whereType<Map>()
                .map((item) => item.cast<String, dynamic>())
                .toList();
            final lifeAreas =
                ((data?['lifeAreas'] as Map<String, dynamic>?)?['areas']
                            as List<dynamic>? ??
                        const [])
                    .whereType<Map>()
                    .map((item) => item.cast<String, dynamic>())
                    .toList();
            final companionScore =
                data?['companionScore'] as Map<String, dynamic>?;
            final timeline = (data?['timeline'] as List<dynamic>? ?? const [])
                .whereType<Map>()
                .map((item) => item.cast<String, dynamic>())
                .toList();
            final topWins = timeline
                .where(
                  (item) =>
                      item['type'] == 'win' || item['type'] == 'milestone',
                )
                .take(3)
                .toList();
            final topConcerns = timeline
                .where(
                  (item) =>
                      item['type'] == 'recurring_concern' ||
                      item['type'] == 'failure',
                )
                .take(3)
                .toList();

            if (snapshot.connectionState == ConnectionState.waiting &&
                data == null) {
              return const Center(child: CircularProgressIndicator());
            }

            return ListView(
              padding: const EdgeInsets.fromLTRB(20, 24, 20, 96),
              children: [
                _HeroCard(
                  title:
                      'Your companion is learning your whole life, not just your tasks.',
                  subtitle:
                      'Weekly patterns, monthly direction, life-area balance, and follow-ups in one place.',
                  accent: state.companionEmotion?['emotion']?.toString(),
                ),
                const SizedBox(height: 18),
                LayoutBuilder(
                  builder: (context, constraints) {
                    final wide = constraints.maxWidth >= 920;
                    final cards = [
                      _InsightCard(
                        title: 'This week',
                        icon: Icons.calendar_view_week_rounded,
                        child: _PeriodInsightBlock(data: weeklyInsights),
                      ),
                      _InsightCard(
                        title: 'This month',
                        icon: Icons.calendar_month_rounded,
                        child: _PeriodInsightBlock(data: monthlyInsights),
                      ),
                      _InsightCard(
                        title: 'Life-area depth',
                        icon: Icons.hub_rounded,
                        child: _DeepLifeAreaBlock(data: deepLifeAreas),
                      ),
                    ];
                    if (!wide) {
                      return Column(children: cards);
                    }
                    return Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(child: cards[0]),
                        const SizedBox(width: 16),
                        Expanded(child: cards[1]),
                        const SizedBox(width: 16),
                        Expanded(child: cards[2]),
                      ],
                    );
                  },
                ),
                const SizedBox(height: 2),
                LayoutBuilder(
                  builder: (context, constraints) {
                    final wide = constraints.maxWidth >= 920;
                    final firstRow = [
                      _InsightCard(
                        title: 'Companion score',
                        icon: Icons.star_rounded,
                        child: _CompanionScoreBlock(score: companionScore),
                      ),
                      _InsightCard(
                        title: 'Life area balance',
                        icon: Icons.balance_rounded,
                        child: _LifeAreaBalanceBlock(areas: lifeAreas),
                      ),
                    ];
                    final secondRow = [
                      _InsightCard(
                        title: 'Mood trend',
                        icon: Icons.favorite_outline_rounded,
                        child: _MiniBarChart(
                          counts: moodCounts,
                          emptyLabel: 'No reflections yet',
                        ),
                      ),
                      _InsightCard(
                        title: 'Goal progress',
                        icon: Icons.flag_rounded,
                        child: _GoalProgressBlock(
                          counts: goalCounts,
                          total: goals.length,
                        ),
                      ),
                    ];
                    final thirdRow = [
                      _InsightCard(
                        title: 'Weekly review',
                        icon: Icons.auto_stories_rounded,
                        child: weeklyReview == null
                            ? const _EmptyBlock(text: 'No weekly review yet.')
                            : _WeeklyReviewBlock(review: weeklyReview),
                      ),
                      _InsightCard(
                        title: 'Due follow-ups',
                        icon: Icons.schedule_rounded,
                        child: followups.isEmpty
                            ? const _EmptyBlock(
                                text: 'No follow-ups due right now.',
                              )
                            : _FollowUpListBlock(followups: followups),
                      ),
                    ];
                    final fourthRow = [
                      _InsightCard(
                        title: 'Recent wins',
                        icon: Icons.celebration_rounded,
                        child: topWins.isEmpty
                            ? const _EmptyBlock(
                                text: 'No recent wins logged yet.',
                              )
                            : _TimelinePreviewBlock(items: topWins),
                      ),
                      _InsightCard(
                        title: 'Recurring concerns',
                        icon: Icons.warning_amber_rounded,
                        child: topConcerns.isEmpty
                            ? const _EmptyBlock(
                                text: 'No recurring concerns identified yet.',
                              )
                            : _TimelinePreviewBlock(items: topConcerns),
                      ),
                    ];
                    if (!wide) {
                      return Column(
                        children: [
                          ...firstRow,
                          const SizedBox(height: 16),
                          ...secondRow,
                          const SizedBox(height: 16),
                          ...thirdRow,
                          const SizedBox(height: 16),
                          ...fourthRow,
                        ],
                      );
                    }
                    return Column(
                      children: [
                        Row(
                          children: [
                            Expanded(child: firstRow[0]),
                            const SizedBox(width: 16),
                            Expanded(child: firstRow[1]),
                          ],
                        ),
                        const SizedBox(height: 16),
                        Row(
                          children: [
                            Expanded(child: secondRow[0]),
                            const SizedBox(width: 16),
                            Expanded(child: secondRow[1]),
                          ],
                        ),
                        const SizedBox(height: 16),
                        Row(
                          children: [
                            Expanded(child: thirdRow[0]),
                            const SizedBox(width: 16),
                            Expanded(child: thirdRow[1]),
                          ],
                        ),
                        const SizedBox(height: 16),
                        Row(
                          children: [
                            Expanded(child: fourthRow[0]),
                            const SizedBox(width: 16),
                            Expanded(child: fourthRow[1]),
                          ],
                        ),
                      ],
                    );
                  },
                ),
                const SizedBox(height: 16),
                _InsightCard(
                  title: 'Memory highlights',
                  icon: Icons.memory_rounded,
                  child: Column(
                    children: [
                      ...memories
                          .take(4)
                          .map(
                            (memory) => _MemoryRow(
                              memory: memory as Map<String, dynamic>,
                            ),
                          ),
                      if (sessions.isNotEmpty) ...[
                        const SizedBox(height: 8),
                        _SessionNote(count: sessions.length),
                      ],
                    ],
                  ),
                ),
                const SizedBox(height: 16),
                _InsightCard(
                  title: 'Companion cadence',
                  icon: Icons.chat_bubble_outline_rounded,
                  child: _CadenceBlock(
                    currentEmotion: state.companionEmotion?['emotion']
                        ?.toString(),
                    currentMode: state.companionMode,
                    memoryCount: memoryTypeCounts.values.fold<int>(
                      0,
                      (a, b) => a + b,
                    ),
                    sessionCount: sessions.length,
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

class _HeroCard extends StatelessWidget {
  const _HeroCard({
    required this.title,
    required this.subtitle,
    required this.accent,
  });

  final String title;
  final String subtitle;
  final String? accent;

  @override
  Widget build(BuildContext context) {
    final color = switch (accent) {
      'happy' => const Color(0xFF003B2B),
      'excited' => const Color(0xFFFFC815),
      'sad' || 'anxious' || 'frustrated' => const Color(0xFFBA1A1A),
      _ => const Color(0xFFFFC815),
    };

    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [const Color(0xFFF8F7F3), color.withValues(alpha: 0.06)],
        ),
        borderRadius: BorderRadius.circular(30),
        border: Border.all(color: Colors.white.withValues(alpha: 0.78)),
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
              fontSize: 28,
              fontWeight: FontWeight.w800,
              color: Color(0xFF1B1C1A),
            ),
          ),
          const SizedBox(height: 8),
          Text(
            subtitle,
            style: const TextStyle(
              fontSize: 14,
              height: 1.5,
              color: Color(0xFF575C6B),
            ),
          ),
        ],
      ),
    );
  }
}

class _CompanionScoreBlock extends StatelessWidget {
  const _CompanionScoreBlock({required this.score});

  final Map<String, dynamic>? score;

  @override
  Widget build(BuildContext context) {
    if (score == null || score?['overall'] == null) {
      return const _EmptyBlock(text: 'Not enough data yet.');
    }
    final overall = score?['overall'] as num? ?? 0;
    final explanation =
        score?['explanation']?.toString() ??
        score?['message']?.toString() ??
        '';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Text(
              overall.toStringAsFixed(0),
              style: const TextStyle(
                fontSize: 40,
                fontWeight: FontWeight.w900,
                color: Color(0xFF1B1C1A),
              ),
            ),
            const SizedBox(width: 6),
            const Padding(
              padding: EdgeInsets.only(bottom: 6),
              child: Text(
                '/100',
                style: TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w700,
                  color: Color(0xFF575C6B),
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 8),
        _MetricRow(label: 'Consistency', value: score?['consistency'] as num?),
        _MetricRow(label: 'Energy', value: score?['energy'] as num?),
        _MetricRow(label: 'Focus', value: score?['focus'] as num?),
        _MetricRow(
          label: 'Goal progress',
          value: score?['goal_progress'] as num?,
        ),
        _MetricRow(
          label: 'Reflection frequency',
          value: score?['reflection_frequency'] as num?,
        ),
        if (explanation.isNotEmpty) ...[
          const SizedBox(height: 10),
          Text(
            explanation,
            style: const TextStyle(
              fontSize: 13,
              height: 1.5,
              color: Color(0xFF4B444D),
            ),
          ),
        ],
      ],
    );
  }
}

class _PeriodInsightBlock extends StatelessWidget {
  const _PeriodInsightBlock({required this.data});

  final Map<String, dynamic>? data;

  @override
  Widget build(BuildContext context) {
    if (data == null || data?['sparse'] == true) {
      return const _EmptyBlock(
        text:
            'Not enough real activity yet. AiPal will summarize this once there is signal.',
      );
    }
    final summary = data?['summary'] as Map<String, dynamic>? ?? const {};
    final business = data?['business'] as Map<String, dynamic>? ?? const {};
    final growth = data?['growth'] as Map<String, dynamic>? ?? const {};
    final narrative = (data?['narrative'] as Map<String, dynamic>?)?['message']
        ?.toString();
    final wins = (growth['wins'] as List<dynamic>? ?? const [])
        .take(3)
        .toList();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (narrative != null && narrative.isNotEmpty) ...[
          Text(
            narrative,
            style: const TextStyle(
              fontSize: 13,
              height: 1.5,
              color: Color(0xFF30343F),
            ),
          ),
          const SizedBox(height: 12),
        ],
        _MiniStatLine(
          label: 'Tasks',
          value: summary['tasks']?.toString() ?? '0',
        ),
        _MiniStatLine(
          label: 'Meetings',
          value: summary['meetings']?.toString() ?? '0',
        ),
        _MiniStatLine(
          label: 'Focus',
          value: '${summary['focus_minutes'] ?? 0}m',
        ),
        _MiniStatLine(
          label: 'Business items',
          value: '${business['tasks'] ?? 0}',
        ),
        if (wins.isNotEmpty) ...[
          const SizedBox(height: 10),
          const Text(
            'Signals',
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w800,
              color: Color(0xFF003B2B),
            ),
          ),
          const SizedBox(height: 4),
          ...wins.map(
            (win) => Text(
              '• ${win.toString()}',
              style: const TextStyle(
                fontSize: 13,
                height: 1.45,
                color: Color(0xFF30343F),
              ),
            ),
          ),
        ],
      ],
    );
  }
}

class _DeepLifeAreaBlock extends StatelessWidget {
  const _DeepLifeAreaBlock({required this.data});

  final Map<String, dynamic>? data;

  @override
  Widget build(BuildContext context) {
    final topAreas = (data?['top_areas'] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((item) => item.cast<String, dynamic>())
        .toList();
    final narrative = (data?['narrative'] as Map<String, dynamic>?)?['message']
        ?.toString();
    if (data == null || data?['sparse'] == true || topAreas.isEmpty) {
      return const _EmptyBlock(text: 'No strong life-area pattern yet.');
    }
    return Column(
      children: [
        if (narrative != null && narrative.isNotEmpty) ...[
          Text(
            narrative,
            style: const TextStyle(
              fontSize: 13,
              height: 1.5,
              color: Color(0xFF30343F),
            ),
          ),
          const SizedBox(height: 12),
        ],
        ...topAreas.take(3).map((area) {
          final label =
              area['life_area']?.toString().replaceAll('_', ' ') ?? 'Area';
          final count =
              (area['memory_count'] ?? 0) +
              (area['task_count'] ?? 0) +
              (area['goal_count'] ?? 0);
          return Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    label,
                    style: const TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w800,
                      color: Color(0xFF1B1C1A),
                    ),
                  ),
                ),
                _Pill(label: '$count signals'),
              ],
            ),
          );
        }),
      ],
    );
  }
}

class _MiniStatLine extends StatelessWidget {
  const _MiniStatLine({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: [
          Expanded(
            child: Text(
              label,
              style: const TextStyle(fontSize: 13, color: Color(0xFF575C6B)),
            ),
          ),
          Text(
            value,
            style: const TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w900,
              color: Color(0xFF003B2B),
            ),
          ),
        ],
      ),
    );
  }
}

class _LifeAreaBalanceBlock extends StatelessWidget {
  const _LifeAreaBalanceBlock({required this.areas});

  final List<Map<String, dynamic>> areas;

  @override
  Widget build(BuildContext context) {
    if (areas.isEmpty) {
      return const _EmptyBlock(text: 'No life-area data yet.');
    }
    return Column(
      children: areas.take(4).map((area) {
        final balance = (area['balance_score'] as num?)?.toDouble() ?? 0;
        return Padding(
          padding: const EdgeInsets.only(bottom: 10),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      area['life_area']?.toString().replaceAll('_', ' ') ?? '',
                      style: const TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                        color: Color(0xFF1B1C1A),
                      ),
                    ),
                  ),
                  Text(
                    '${balance.toStringAsFixed(0)}%',
                    style: const TextStyle(
                      fontSize: 12,
                      color: Color(0xFF575C6B),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 6),
              ClipRRect(
                borderRadius: BorderRadius.circular(999),
                child: LinearProgressIndicator(
                  value: balance / 100,
                  minHeight: 8,
                  backgroundColor: const Color(0xFFE6E0D8),
                  valueColor: const AlwaysStoppedAnimation<Color>(
                    Color(0xFF003B2B),
                  ),
                ),
              ),
            ],
          ),
        );
      }).toList(),
    );
  }
}

class _MetricRow extends StatelessWidget {
  const _MetricRow({required this.label, required this.value});

  final String label;
  final num? value;

  @override
  Widget build(BuildContext context) {
    final display = value == null ? '—' : value!.toStringAsFixed(0);
    return Padding(
      padding: const EdgeInsets.only(top: 6),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            label,
            style: const TextStyle(fontSize: 12, color: Color(0xFF575C6B)),
          ),
          Text(
            display,
            style: const TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w700,
              color: Color(0xFF1B1C1A),
            ),
          ),
        ],
      ),
    );
  }
}

class _WeeklyReviewBlock extends StatelessWidget {
  const _WeeklyReviewBlock({required this.review});

  final Map<String, dynamic> review;

  @override
  Widget build(BuildContext context) {
    final summary = review['summary']?.toString() ?? '';
    final wins =
        (review['wins'] as List?)?.map((e) => e.toString()).take(3).toList() ??
        const [];
    final challenges =
        (review['challenges'] as List?)
            ?.map((e) => e.toString())
            .take(2)
            .toList() ??
        const [];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (summary.isNotEmpty)
          Text(
            summary,
            style: const TextStyle(
              fontSize: 13,
              height: 1.5,
              color: Color(0xFF30343F),
            ),
          ),
        if (wins.isNotEmpty) ...[
          const SizedBox(height: 10),
          const Text(
            'Wins',
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w700,
              color: Color(0xFF003B2B),
            ),
          ),
          const SizedBox(height: 4),
          ...wins.map(
            (item) => Text(
              '• $item',
              style: const TextStyle(fontSize: 13, height: 1.45),
            ),
          ),
        ],
        if (challenges.isNotEmpty) ...[
          const SizedBox(height: 10),
          const Text(
            'Challenges',
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w700,
              color: Color(0xFF8C2B3B),
            ),
          ),
          const SizedBox(height: 4),
          ...challenges.map(
            (item) => Text(
              '• $item',
              style: const TextStyle(fontSize: 13, height: 1.45),
            ),
          ),
        ],
      ],
    );
  }
}

class _FollowUpListBlock extends StatelessWidget {
  const _FollowUpListBlock({required this.followups});

  final List<Map<String, dynamic>> followups;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: followups.take(3).map((item) {
        return Padding(
          padding: const EdgeInsets.only(bottom: 10),
          child: Container(
            width: double.infinity,
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: const Color(0xFFFFC815).withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(16),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  item['prompt']?.toString() ?? 'Follow up',
                  style: const TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w700,
                    color: Color(0xFFFFC815),
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  item['title']?.toString() ?? '',
                  style: const TextStyle(
                    fontSize: 12,
                    color: Color(0xFF575C6B),
                  ),
                ),
              ],
            ),
          ),
        );
      }).toList(),
    );
  }
}

class _TimelinePreviewBlock extends StatelessWidget {
  const _TimelinePreviewBlock({required this.items});

  final List<Map<String, dynamic>> items;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: items.take(3).map((item) {
        return Padding(
          padding: const EdgeInsets.only(bottom: 10),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 10,
                height: 10,
                margin: const EdgeInsets.only(top: 5),
                decoration: const BoxDecoration(
                  color: _timelineDotColor,
                  shape: BoxShape.circle,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      item['title']?.toString() ?? 'Memory',
                      style: const TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                        color: Color(0xFF1B1C1A),
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      item['content']?.toString() ?? '',
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 12,
                        height: 1.4,
                        color: Color(0xFF575C6B),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        );
      }).toList(),
    );
  }
}

class _InsightCard extends StatelessWidget {
  const _InsightCard({
    required this.title,
    required this.icon,
    required this.child,
  });

  final String title;
  final IconData icon;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.56),
        borderRadius: BorderRadius.circular(28),
        border: Border.all(color: Colors.white.withValues(alpha: 0.84)),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF1A1F2C).withValues(alpha: 0.04),
            blurRadius: 28,
            offset: const Offset(0, 12),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, size: 20, color: const Color(0xFFFFC815)),
              const SizedBox(width: 10),
              Text(
                title,
                style: const TextStyle(
                  fontFamily: 'Manrope',
                  fontSize: 20,
                  fontWeight: FontWeight.w800,
                  color: Color(0xFF1B1C1A),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          child,
        ],
      ),
    );
  }
}

class _MiniBarChart extends StatelessWidget {
  const _MiniBarChart({required this.counts, required this.emptyLabel});

  final Map<String, int> counts;
  final String emptyLabel;

  @override
  Widget build(BuildContext context) {
    if (counts.isEmpty) {
      return _EmptyBlock(text: emptyLabel);
    }
    final maxCount = math.max(1, counts.values.reduce(math.max));
    final entries = counts.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));
    return Column(
      children: entries.take(5).map((entry) {
        final progress = entry.value / maxCount;
        return Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      entry.key,
                      style: const TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                        color: Color(0xFF1B1C1A),
                      ),
                    ),
                  ),
                  Text(
                    '${entry.value}',
                    style: const TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w800,
                      color: Color(0xFFFFC815),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              ClipRRect(
                borderRadius: BorderRadius.circular(999),
                child: LinearProgressIndicator(
                  value: progress.clamp(0, 1),
                  minHeight: 8,
                  backgroundColor: const Color(0xFFEFEFEA),
                  valueColor: const AlwaysStoppedAnimation<Color>(
                    Color(0xFFFFC815),
                  ),
                ),
              ),
            ],
          ),
        );
      }).toList(),
    );
  }
}

class _GoalProgressBlock extends StatelessWidget {
  const _GoalProgressBlock({required this.counts, required this.total});

  final Map<String, int> counts;
  final int total;

  @override
  Widget build(BuildContext context) {
    final active = counts['active'] ?? 0;
    final completed = counts['completed'] ?? 0;
    final archived = counts['archived'] ?? 0;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _ProgressRow(
          label: 'Active',
          value: active,
          color: const Color(0xFFFFC815),
        ),
        const SizedBox(height: 10),
        _ProgressRow(
          label: 'Completed',
          value: completed,
          color: const Color(0xFF003B2B),
        ),
        const SizedBox(height: 10),
        _ProgressRow(
          label: 'Archived',
          value: archived,
          color: const Color(0xFFBA1A1A),
        ),
        const SizedBox(height: 14),
        Text(
          '$total total goals',
          style: const TextStyle(fontSize: 12.5, color: Color(0xFF575C6B)),
        ),
      ],
    );
  }
}

class _ProgressRow extends StatelessWidget {
  const _ProgressRow({
    required this.label,
    required this.value,
    required this.color,
  });

  final String label;
  final int value;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: Text(
            label,
            style: const TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w700,
              color: Color(0xFF1B1C1A),
            ),
          ),
        ),
        Text(
          '$value',
          style: TextStyle(
            fontSize: 12.5,
            fontWeight: FontWeight.w800,
            color: color,
          ),
        ),
      ],
    );
  }
}

class _MemoryRow extends StatelessWidget {
  const _MemoryRow({required this.memory});

  final Map<String, dynamic> memory;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFFFBFAF7),
        borderRadius: BorderRadius.circular(22),
        border: Border.all(color: const Color(0xFFE6E1D6)),
      ),
      child: Row(
        children: [
          Container(
            width: 38,
            height: 38,
            decoration: BoxDecoration(
              color: const Color(0xFFFFF2B8).withValues(alpha: 0.75),
              borderRadius: BorderRadius.circular(14),
            ),
            child: const Icon(
              Icons.memory_rounded,
              color: Color(0xFFFFC815),
              size: 20,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  memory['title']?.toString() ?? 'Memory',
                  style: const TextStyle(
                    fontSize: 13.5,
                    fontWeight: FontWeight.w800,
                    color: Color(0xFF1B1C1A),
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  memory['content']?.toString() ?? '',
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontSize: 12.5,
                    height: 1.45,
                    color: Color(0xFF575C6B),
                  ),
                ),
              ],
            ),
          ),
          if ((memory['life_area']?.toString() ?? '').isNotEmpty)
            _Pill(label: memory['life_area'].toString()),
        ],
      ),
    );
  }
}

class _SessionNote extends StatelessWidget {
  const _SessionNote({required this.count});

  final int count;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Text(
        '$count conversation sessions stored',
        style: const TextStyle(fontSize: 12.5, color: Color(0xFF575C6B)),
      ),
    );
  }
}

class _CadenceBlock extends StatelessWidget {
  const _CadenceBlock({
    required this.currentEmotion,
    required this.currentMode,
    required this.memoryCount,
    required this.sessionCount,
  });

  final String? currentEmotion;
  final String? currentMode;
  final int memoryCount;
  final int sessionCount;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _Pill(label: 'Mode: ${currentMode ?? 'companion'}'),
        const SizedBox(height: 10),
        Text(
          'Current mood: ${currentEmotion ?? 'neutral'}',
          style: const TextStyle(
            fontSize: 13.5,
            fontWeight: FontWeight.w600,
            color: Color(0xFF1B1C1A),
          ),
        ),
        const SizedBox(height: 6),
        Text(
          '$memoryCount tracked memories across $sessionCount conversation sessions.',
          style: const TextStyle(
            fontSize: 12.5,
            height: 1.45,
            color: Color(0xFF575C6B),
          ),
        ),
      ],
    );
  }
}

class _EmptyBlock extends StatelessWidget {
  const _EmptyBlock({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFFF8F7F3),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: const Color(0xFFE6E1D6)),
      ),
      child: Text(
        text,
        style: const TextStyle(
          fontSize: 13,
          height: 1.45,
          color: Color(0xFF575C6B),
        ),
      ),
    );
  }
}

class _Pill extends StatelessWidget {
  const _Pill({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: const Color(0xFFFFF2B8).withValues(alpha: 0.45),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        label,
        style: const TextStyle(
          fontSize: 11.5,
          fontWeight: FontWeight.w800,
          color: Color(0xFFFFC815),
        ),
      ),
    );
  }
}
