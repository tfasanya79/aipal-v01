import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/app_state.dart';

class LifeMapScreen extends StatefulWidget {
  const LifeMapScreen({super.key});

  @override
  State<LifeMapScreen> createState() => _LifeMapScreenState();
}

class _LifeMapScreenState extends State<LifeMapScreen> {
  late Future<Map<String, dynamic>> _future;
  late Future<Map<String, dynamic>> _briefingFuture;

  @override
  void initState() {
    super.initState();
    _future = context.read<AppState>().api.getLifeMap();
    _briefingFuture = context.read<AppState>().api.getLifeMapBriefing();
  }

  Future<void> _refresh() async {
    setState(() {
      _future = context.read<AppState>().api.getLifeMap();
      _briefingFuture = context.read<AppState>().api.getLifeMapBriefing();
    });
    await _future;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFFAF9F5),
      body: Stack(
        children: [
          const _LifeMapAtmosphere(),
          SafeArea(
            child: FutureBuilder<Map<String, dynamic>>(
              future: _future,
              builder: (context, snapshot) {
                if (snapshot.connectionState == ConnectionState.waiting) {
                  return const _LoadingLifeMap();
                }
                if (snapshot.hasError) {
                  return _ErrorState(onRetry: _refresh);
                }
                final payload = snapshot.data ?? const <String, dynamic>{};
                final areas = (payload['areas'] as List<dynamic>? ?? const [])
                    .whereType<Map<String, dynamic>>()
                    .toList();
                return RefreshIndicator(
                  onRefresh: _refresh,
                  color: const Color(0xFF003B2B),
                  child: CustomScrollView(
                    physics: const AlwaysScrollableScrollPhysics(),
                    slivers: [
                      SliverPadding(
                        padding: const EdgeInsets.fromLTRB(24, 24, 24, 12),
                        sliver: SliverToBoxAdapter(
                          child: _HeroCard(
                            sparse: payload['sparse'] == true,
                            totalActivity:
                                (payload['total_activity'] as num?)?.toInt() ??
                                0,
                            suggestedActivity:
                                (payload['suggested_activity'] as num?)
                                    ?.toInt() ??
                                0,
                          ),
                        ),
                      ),
                      if (payload['sparse'] == true)
                        const SliverPadding(
                          padding: EdgeInsets.fromLTRB(24, 0, 24, 12),
                          sliver: SliverToBoxAdapter(child: _SparseNote()),
                        ),
                      SliverPadding(
                        padding: const EdgeInsets.fromLTRB(24, 0, 24, 12),
                        sliver: SliverToBoxAdapter(
                          child: _BrainBriefCard(future: _briefingFuture),
                        ),
                      ),
                      SliverPadding(
                        padding: const EdgeInsets.fromLTRB(24, 8, 24, 32),
                        sliver: SliverGrid.builder(
                          gridDelegate:
                              SliverGridDelegateWithFixedCrossAxisCount(
                                crossAxisCount:
                                    MediaQuery.sizeOf(context).width >= 840
                                    ? 2
                                    : 1,
                                mainAxisSpacing: 16,
                                crossAxisSpacing: 16,
                                mainAxisExtent: 214,
                              ),
                          itemCount: areas.length,
                          itemBuilder: (context, index) {
                            return _LifeAreaCard(
                              area: areas[index],
                              onTap: () {
                                final id =
                                    areas[index]['life_area']?.toString() ?? '';
                                if (id.isEmpty) return;
                                Navigator.of(context).push(
                                  MaterialPageRoute(
                                    builder: (_) =>
                                        _LifeAreaDetailScreen(lifeArea: id),
                                  ),
                                );
                              },
                            );
                          },
                        ),
                      ),
                    ],
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _LifeAreaDetailScreen extends StatefulWidget {
  const _LifeAreaDetailScreen({required this.lifeArea});

  final String lifeArea;

  @override
  State<_LifeAreaDetailScreen> createState() => _LifeAreaDetailScreenState();
}

class _LifeAreaDetailScreenState extends State<_LifeAreaDetailScreen> {
  late Future<Map<String, dynamic>> _future;
  late Future<Map<String, dynamic>> _briefingFuture;

  @override
  void initState() {
    super.initState();
    _future = context.read<AppState>().api.getLifeAreaDetail(widget.lifeArea);
    _briefingFuture = context.read<AppState>().api.getLifeAreaBriefing(
      widget.lifeArea,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFFAF9F5),
      body: Stack(
        children: [
          const _LifeMapAtmosphere(),
          SafeArea(
            child: FutureBuilder<Map<String, dynamic>>(
              future: _future,
              builder: (context, snapshot) {
                if (snapshot.connectionState == ConnectionState.waiting) {
                  return const _LoadingLifeMap();
                }
                if (snapshot.hasError) {
                  return _ErrorState(
                    onRetry: () async {
                      setState(() {
                        _future = context
                            .read<AppState>()
                            .api
                            .getLifeAreaDetail(widget.lifeArea);
                        _briefingFuture = context
                            .read<AppState>()
                            .api
                            .getLifeAreaBriefing(widget.lifeArea);
                      });
                      await _future;
                    },
                  );
                }
                final area = snapshot.data ?? const <String, dynamic>{};
                return CustomScrollView(
                  slivers: [
                    SliverPadding(
                      padding: const EdgeInsets.fromLTRB(24, 24, 24, 12),
                      sliver: SliverToBoxAdapter(
                        child: _DetailHeader(area: area),
                      ),
                    ),
                    SliverPadding(
                      padding: const EdgeInsets.fromLTRB(24, 0, 24, 32),
                      sliver: SliverList(
                        delegate: SliverChildListDelegate([
                          _BrainBriefCard(future: _briefingFuture),
                          const SizedBox(height: 14),
                          _DetailSection(
                            title: 'Patterns',
                            items: _strings(area['patterns']),
                            empty:
                                'No patterns yet. AiPal will only show this when real data exists.',
                          ),
                          _DetailSection(
                            title: 'Suggested links',
                            items: _suggestedTitles(area['suggested_items']),
                            empty: 'No uncertain links need review here.',
                          ),
                          _DetailSection(
                            title: 'Goals',
                            items: _titles(area['goals']),
                            empty: 'No goals linked here yet.',
                          ),
                          _DetailSection(
                            title: 'Tasks',
                            items: _titles(area['tasks']),
                            empty: 'No tasks linked here yet.',
                          ),
                          _DetailSection(
                            title: 'Habits',
                            items: _names(area['habits']),
                            empty: 'No habits linked here yet.',
                          ),
                          _DetailSection(
                            title: 'Wins',
                            items: _titles(area['wins']),
                            empty: 'No wins saved here yet.',
                          ),
                          _DetailSection(
                            title: 'Challenges',
                            items: _titles(area['challenges']),
                            empty: 'No challenges saved here yet.',
                          ),
                          _DetailSection(
                            title: 'Memories',
                            items: _titles(area['memories']),
                            empty: 'No approved memories linked here yet.',
                          ),
                        ]),
                      ),
                    ),
                  ],
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _LifeMapAtmosphere extends StatelessWidget {
  const _LifeMapAtmosphere();

  @override
  Widget build(BuildContext context) {
    return const Stack(
      children: [
        Positioned(
          top: -120,
          right: -80,
          child: _BlurBlob(color: Color(0x33FFC815), size: 260),
        ),
        Positioned(
          bottom: -90,
          left: -60,
          child: _BlurBlob(color: Color(0x33326667), size: 240),
        ),
      ],
    );
  }
}

class _HeroCard extends StatelessWidget {
  const _HeroCard({
    required this.sparse,
    required this.totalActivity,
    required this.suggestedActivity,
  });

  final bool sparse;
  final int totalActivity;
  final int suggestedActivity;

  @override
  Widget build(BuildContext context) {
    return _GlassCard(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              _IconBubble(
                icon: Icons.auto_awesome_mosaic_rounded,
                color: Color(0xFFFFC815),
              ),
              SizedBox(width: 14),
              Expanded(
                child: Text(
                  'Life Map',
                  style: TextStyle(
                    color: Color(0xFF24182C),
                    fontSize: 30,
                    fontWeight: FontWeight.w800,
                    letterSpacing: -0.6,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Text(
            sparse
                ? 'A clean map of your life areas. As AiPal learns from real goals, memories, habits, and reflections, this becomes richer.'
                : 'A connected overview of your goals, habits, memories, reflections, and relationship context.',
            style: const TextStyle(
              color: Color(0xFF5D5264),
              fontSize: 16,
              height: 1.45,
            ),
          ),
          const SizedBox(height: 18),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _MetricPill(label: '$totalActivity linked signals'),
              if (suggestedActivity > 0)
                _MetricPill(label: '$suggestedActivity suggested links'),
            ],
          ),
        ],
      ),
    );
  }
}

class _SparseNote extends StatelessWidget {
  const _SparseNote();

  @override
  Widget build(BuildContext context) {
    return const _GlassCard(
      padding: EdgeInsets.all(18),
      child: Row(
        children: [
          Icon(Icons.info_outline_rounded, color: Color(0xFF003B2B)),
          SizedBox(width: 12),
          Expanded(
            child: Text(
              'No fake data here. Start by adding a goal, habit, memory, task, or reflection, and AiPal will connect it to your Life Map.',
              style: TextStyle(color: Color(0xFF4E5A5A), height: 1.35),
            ),
          ),
        ],
      ),
    );
  }
}

class _BrainBriefCard extends StatelessWidget {
  const _BrainBriefCard({required this.future});

  final Future<Map<String, dynamic>> future;

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<Map<String, dynamic>>(
      future: future,
      builder: (context, snapshot) {
        final message = snapshot.data?['message']?.toString().trim() ?? '';
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const _GlassCard(
            padding: EdgeInsets.all(18),
            child: Row(
              children: [
                SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    color: Color(0xFF003B2B),
                  ),
                ),
                SizedBox(width: 12),
                Expanded(
                  child: Text(
                    'AiPal is reading the map gently...',
                    style: TextStyle(color: Color(0xFF6B626D)),
                  ),
                ),
              ],
            ),
          );
        }
        if (message.isEmpty) {
          return const SizedBox.shrink();
        }
        return _GlassCard(
          padding: const EdgeInsets.all(18),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const _IconBubble(
                icon: Icons.psychology_alt_rounded,
                color: Color(0xFFFFC815),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'AiPal read',
                      style: TextStyle(
                        color: Color(0xFF24182C),
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      message,
                      style: const TextStyle(
                        color: Color(0xFF5D5264),
                        height: 1.42,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _LifeAreaCard extends StatelessWidget {
  const _LifeAreaCard({required this.area, required this.onTap});

  final Map<String, dynamic> area;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final progress = ((area['progress'] as num?)?.toDouble() ?? 0).clamp(
      0,
      100,
    );
    final label = area['label']?.toString() ?? 'Life Area';
    return _GlassCard(
      onTap: onTap,
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              _IconBubble(icon: _iconFor(area['life_area']?.toString())),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  label,
                  style: const TextStyle(
                    color: Color(0xFF24182C),
                    fontSize: 20,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ),
              const Icon(Icons.chevron_right_rounded, color: Color(0xFFFFC815)),
            ],
          ),
          const SizedBox(height: 18),
          ClipRRect(
            borderRadius: BorderRadius.circular(999),
            child: LinearProgressIndicator(
              value: progress / 100,
              minHeight: 9,
              backgroundColor: const Color(0x22326667),
              color: const Color(0xFF003B2B),
            ),
          ),
          const SizedBox(height: 10),
          Text(
            '${progress.round()}% activity signal',
            style: const TextStyle(
              color: Color(0xFFFFC815),
              fontWeight: FontWeight.w700,
            ),
          ),
          const Spacer(),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _MetricPill(label: '${_int(area['goal_count'])} goals'),
              _MetricPill(label: '${_int(area['task_count'])} tasks'),
              _MetricPill(label: '${_int(area['habit_count'])} habits'),
              _MetricPill(label: '${_int(area['memory_count'])} memories'),
              if (_int(area['suggested_count']) > 0)
                _MetricPill(
                  label: '${_int(area['suggested_count'])} suggested',
                ),
            ],
          ),
        ],
      ),
    );
  }
}

class _DetailHeader extends StatelessWidget {
  const _DetailHeader({required this.area});

  final Map<String, dynamic> area;

  @override
  Widget build(BuildContext context) {
    final progress = ((area['progress'] as num?)?.toDouble() ?? 0).clamp(
      0,
      100,
    );
    return _GlassCard(
      padding: const EdgeInsets.all(22),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              IconButton.filledTonal(
                onPressed: () => Navigator.of(context).maybePop(),
                icon: const Icon(Icons.arrow_back_rounded),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  area['label']?.toString() ?? 'Life Area',
                  style: const TextStyle(
                    color: Color(0xFF24182C),
                    fontSize: 28,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 18),
          ClipRRect(
            borderRadius: BorderRadius.circular(999),
            child: LinearProgressIndicator(
              value: progress / 100,
              minHeight: 10,
              backgroundColor: const Color(0x22326667),
              color: const Color(0xFF003B2B),
            ),
          ),
          const SizedBox(height: 14),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _MetricPill(label: '${_int(area['goal_count'])} goals'),
              _MetricPill(label: '${_int(area['task_count'])} tasks'),
              _MetricPill(label: '${_int(area['win_count'])} wins'),
              _MetricPill(label: '${_int(area['challenge_count'])} challenges'),
              if (_int(area['suggested_count']) > 0)
                _MetricPill(
                  label: '${_int(area['suggested_count'])} suggested',
                ),
            ],
          ),
        ],
      ),
    );
  }
}

class _DetailSection extends StatelessWidget {
  const _DetailSection({
    required this.title,
    required this.items,
    required this.empty,
  });

  final String title;
  final List<String> items;
  final String empty;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: _GlassCard(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              title,
              style: const TextStyle(
                color: Color(0xFF24182C),
                fontSize: 18,
                fontWeight: FontWeight.w800,
              ),
            ),
            const SizedBox(height: 12),
            if (items.isEmpty)
              Text(
                empty,
                style: const TextStyle(color: Color(0xFF6B626D), height: 1.4),
              )
            else
              ...items.map(
                (item) => Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Icon(
                        Icons.check_circle_outline_rounded,
                        size: 18,
                        color: Color(0xFF003B2B),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(
                          item,
                          style: const TextStyle(
                            color: Color(0xFF3D3344),
                            height: 1.35,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _GlassCard extends StatelessWidget {
  const _GlassCard({
    required this.child,
    this.padding = const EdgeInsets.all(16),
    this.onTap,
  });

  final Widget child;
  final EdgeInsetsGeometry padding;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final card = ClipRRect(
      borderRadius: BorderRadius.circular(28),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 18, sigmaY: 18),
        child: Container(
          padding: padding,
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: 0.68),
            borderRadius: BorderRadius.circular(28),
            border: Border.all(color: Colors.white.withValues(alpha: 0.72)),
            boxShadow: const [
              BoxShadow(
                color: Color(0x1A326667),
                blurRadius: 28,
                offset: Offset(0, 18),
              ),
            ],
          ),
          child: child,
        ),
      ),
    );
    if (onTap == null) return card;
    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(28),
        onTap: onTap,
        child: card,
      ),
    );
  }
}

class _IconBubble extends StatelessWidget {
  const _IconBubble({required this.icon, this.color = const Color(0xFF003B2B)});

  final IconData icon;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 46,
      height: 46,
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        shape: BoxShape.circle,
      ),
      child: Icon(icon, color: color),
    );
  }
}

class _MetricPill extends StatelessWidget {
  const _MetricPill({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
      decoration: BoxDecoration(
        color: const Color(0x14326667),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: const Color(0x22326667)),
      ),
      child: Text(
        label,
        style: const TextStyle(
          color: Color(0xFF003B2B),
          fontWeight: FontWeight.w700,
          fontSize: 12,
        ),
      ),
    );
  }
}

class _LoadingLifeMap extends StatelessWidget {
  const _LoadingLifeMap();

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: CircularProgressIndicator(color: Color(0xFF003B2B)),
    );
  }
}

class _ErrorState extends StatelessWidget {
  const _ErrorState({required this.onRetry});

  final Future<void> Function() onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: _GlassCard(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(
                Icons.error_outline_rounded,
                color: Color(0xFFFFC815),
                size: 34,
              ),
              const SizedBox(height: 12),
              const Text(
                'Life Map could not load.',
                style: TextStyle(
                  color: Color(0xFF24182C),
                  fontSize: 18,
                  fontWeight: FontWeight.w800,
                ),
              ),
              const SizedBox(height: 8),
              const Text(
                'Try again in a moment.',
                textAlign: TextAlign.center,
                style: TextStyle(color: Color(0xFF6B626D)),
              ),
              const SizedBox(height: 16),
              FilledButton(
                style: FilledButton.styleFrom(
                  backgroundColor: const Color(0xFF003B2B),
                ),
                onPressed: onRetry,
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _BlurBlob extends StatelessWidget {
  const _BlurBlob({required this.color, required this.size});

  final Color color;
  final double size;

  @override
  Widget build(BuildContext context) {
    return ImageFiltered(
      imageFilter: ImageFilter.blur(sigmaX: 46, sigmaY: 46),
      child: Container(
        width: size,
        height: size,
        decoration: BoxDecoration(color: color, shape: BoxShape.circle),
      ),
    );
  }
}

IconData _iconFor(String? area) {
  return switch (area) {
    'business' => Icons.business_center_rounded,
    'health' => Icons.favorite_border_rounded,
    'finance' => Icons.account_balance_wallet_rounded,
    'learning' => Icons.menu_book_rounded,
    'relationships' => Icons.people_alt_rounded,
    'spiritual' => Icons.self_improvement_rounded,
    'personal_growth' => Icons.trending_up_rounded,
    _ => Icons.auto_awesome_mosaic_rounded,
  };
}

int _int(Object? value) => (value as num?)?.toInt() ?? 0;

List<String> _titles(Object? value) {
  return (value as List<dynamic>? ?? const [])
      .whereType<Map<String, dynamic>>()
      .map((item) => item['title']?.toString() ?? '')
      .where((title) => title.trim().isNotEmpty)
      .toList();
}

List<String> _names(Object? value) {
  return (value as List<dynamic>? ?? const [])
      .whereType<Map<String, dynamic>>()
      .map((item) => item['name']?.toString() ?? '')
      .where((name) => name.trim().isNotEmpty)
      .toList();
}

List<String> _strings(Object? value) {
  return (value as List<dynamic>? ?? const [])
      .map((item) => item.toString())
      .where((item) => item.trim().isNotEmpty)
      .toList();
}

List<String> _suggestedTitles(Object? value) {
  return (value as List<dynamic>? ?? const [])
      .whereType<Map<String, dynamic>>()
      .map((item) {
        final title = (item['title'] ?? item['name'] ?? item['summary'] ?? '')
            .toString()
            .trim();
        final kind = item['kind']?.toString() ?? 'item';
        return title.isEmpty ? '' : '$title ($kind, needs review)';
      })
      .where((title) => title.isNotEmpty)
      .toList();
}
