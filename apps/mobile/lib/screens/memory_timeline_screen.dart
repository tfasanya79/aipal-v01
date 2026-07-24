import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/app_state.dart';

class MemoryTimelineScreen extends StatefulWidget {
  const MemoryTimelineScreen({super.key});

  @override
  State<MemoryTimelineScreen> createState() => _MemoryTimelineScreenState();
}

class _MemoryTimelineScreenState extends State<MemoryTimelineScreen> {
  final _searchController = TextEditingController();
  Future<Map<String, dynamic>>? _future;
  String? _lifeArea;
  String? _type;
  String _query = '';

  static const _lifeAreas = [
    'business',
    'health',
    'finance',
    'learning',
    'relationships',
    'spiritual',
    'personal_growth',
  ];

  static const _types = [
    'important_event',
    'project',
    'relationship',
    'person',
    'recurring_concern',
    'win',
    'failure',
    'decision',
    'milestone',
    'promise',
    'follow_up',
    'emotional_pattern',
  ];

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Future<Map<String, dynamic>> _load() async {
    final api = context.read<AppState>().api;
    if (_lifeArea == null && _type == null) {
      final autobiography = await api.getMemoryAutobiography(limit: 300);
      final items = <dynamic>[];
      for (final year
          in (autobiography['years'] as List<dynamic>? ?? const [])) {
        final yearMap = year as Map;
        for (final month in (yearMap['months'] as List<dynamic>? ?? const [])) {
          final monthMap = month as Map;
          items.addAll(monthMap['items'] as List<dynamic>? ?? const []);
        }
      }
      return {...autobiography, 'items': items, 'source': 'autobiography'};
    }
    final items = await api.getMemoryTimeline(
      lifeArea: _lifeArea,
      type: _type,
      limit: 150,
    );
    return {
      'items': items,
      'source': 'timeline',
      'years': const [],
      'milestones': const [],
    };
  }

  Future<void> _refresh() async {
    setState(() {
      _future = _load();
    });
  }

  void _applyFilters({String? lifeArea, String? type}) {
    setState(() {
      _lifeArea = lifeArea;
      _type = type;
      _future = _load();
    });
  }

  String _searchText(Map<String, dynamic> item) {
    return [
      item['title'],
      item['content'],
      item['type'],
      item['life_area'],
      if (item['entities'] is List)
        ...(item['entities'] as List).map((e) => e.toString()),
    ].whereType<String>().join(' ').toLowerCase();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFFAF9F5),
      body: Stack(
        children: [
          const _Backdrop(),
          SafeArea(
            child: Column(
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(20, 14, 20, 12),
                  child: Row(
                    children: [
                      _HeaderButton(
                        icon: Icons.arrow_back_rounded,
                        onTap: () => Navigator.pop(context),
                      ),
                      const SizedBox(width: 14),
                      const Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'Memory Timeline',
                              style: TextStyle(
                                fontFamily: 'Manrope',
                                fontSize: 28,
                                fontWeight: FontWeight.w800,
                                color: Color(0xFF1B1C1A),
                              ),
                            ),
                            SizedBox(height: 2),
                            Text(
                              'A chronological view of wins, events, concerns, and follow-ups',
                              style: TextStyle(
                                fontSize: 13,
                                color: Color(0xFF575C6B),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(20, 4, 20, 0),
                  child: _GlassPanel(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        TextField(
                          controller: _searchController,
                          onChanged: (value) => setState(
                            () => _query = value.trim().toLowerCase(),
                          ),
                          decoration: InputDecoration(
                            hintText: 'Search titles, entities, or notes',
                            prefixIcon: const Icon(Icons.search_rounded),
                            filled: true,
                            fillColor: Colors.white.withValues(alpha: 0.78),
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(18),
                              borderSide: BorderSide.none,
                            ),
                          ),
                        ),
                        const SizedBox(height: 14),
                        _FilterSection(
                          label: 'Life area',
                          items: [
                            const _FilterChoice(label: 'All', value: null),
                            ..._lifeAreas.map(
                              (area) => _FilterChoice(
                                label: area
                                    .replaceAll('_growth', ' growth')
                                    .replaceAll('_', ' '),
                                value: area,
                              ),
                            ),
                          ],
                          selected: _lifeArea,
                          onSelected: (value) =>
                              _applyFilters(lifeArea: value, type: _type),
                        ),
                        const SizedBox(height: 10),
                        _FilterSection(
                          label: 'Type',
                          items: [
                            const _FilterChoice(label: 'All', value: null),
                            ..._types.map(
                              (type) => _FilterChoice(
                                label: type.replaceAll('_', ' '),
                                value: type,
                              ),
                            ),
                          ],
                          selected: _type,
                          onSelected: (value) =>
                              _applyFilters(lifeArea: _lifeArea, type: value),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                Expanded(
                  child: RefreshIndicator(
                    onRefresh: _refresh,
                    child: FutureBuilder<Map<String, dynamic>>(
                      future: _future,
                      builder: (context, snapshot) {
                        final data = snapshot.data ?? const <String, dynamic>{};
                        final years =
                            (data['years'] as List<dynamic>? ?? const [])
                                .whereType<Map>()
                                .map((item) => item.cast<String, dynamic>())
                                .toList();
                        final milestones =
                            (data['milestones'] as List<dynamic>? ?? const [])
                                .whereType<Map>()
                                .map((item) => item.cast<String, dynamic>())
                                .toList();
                        final items =
                            (data['items'] as List<dynamic>? ?? const [])
                                .whereType<Map>()
                                .map((item) => item.cast<String, dynamic>())
                                .where((item) {
                                  if (_query.isEmpty) return true;
                                  return _searchText(item).contains(_query);
                                })
                                .toList();

                        if (snapshot.connectionState ==
                                ConnectionState.waiting &&
                            snapshot.data == null) {
                          return const Center(
                            child: CircularProgressIndicator(),
                          );
                        }

                        if (items.isEmpty) {
                          return ListView(
                            padding: const EdgeInsets.fromLTRB(20, 20, 20, 80),
                            children: const [_EmptyTimelineState()],
                          );
                        }

                        return ListView.separated(
                          padding: const EdgeInsets.fromLTRB(20, 8, 20, 96),
                          itemCount: items.length + (years.isNotEmpty ? 1 : 0),
                          separatorBuilder: (_, __) =>
                              const SizedBox(height: 12),
                          itemBuilder: (context, index) {
                            if (years.isNotEmpty && index == 0) {
                              return _AutobiographyHeader(
                                years: years,
                                milestones: milestones,
                              );
                            }
                            final itemIndex =
                                index - (years.isNotEmpty ? 1 : 0);
                            return _TimelineItemCard(
                              item: items[itemIndex],
                              isLast: itemIndex == items.length - 1,
                            );
                          },
                        );
                      },
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _Backdrop extends StatelessWidget {
  const _Backdrop();

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        Container(color: const Color(0xFFFAF9F5)),
        Positioned(
          top: -80,
          right: -40,
          child: _Blob(
            color: const Color(0xFFFFC815).withValues(alpha: 0.12),
            size: 220,
          ),
        ),
        Positioned(
          bottom: 120,
          left: -60,
          child: _Blob(
            color: const Color(0xFF003B2B).withValues(alpha: 0.12),
            size: 180,
          ),
        ),
      ],
    );
  }
}

class _Blob extends StatelessWidget {
  const _Blob({required this.color, required this.size});

  final Color color;
  final double size;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(color: color, shape: BoxShape.circle),
    );
  }
}

class _GlassPanel extends StatelessWidget {
  const _GlassPanel({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(28),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
        child: Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: 0.62),
            borderRadius: BorderRadius.circular(28),
            border: Border.all(color: Colors.white.withValues(alpha: 0.75)),
          ),
          child: child,
        ),
      ),
    );
  }
}

class _FilterChoice {
  const _FilterChoice({required this.label, required this.value});

  final String label;
  final String? value;
}

class _FilterSection extends StatelessWidget {
  const _FilterSection({
    required this.label,
    required this.items,
    required this.selected,
    required this.onSelected,
  });

  final String label;
  final List<_FilterChoice> items;
  final String? selected;
  final ValueChanged<String?> onSelected;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: const TextStyle(
            fontSize: 12,
            fontWeight: FontWeight.w700,
            letterSpacing: 0.3,
            color: Color(0xFF575C6B),
          ),
        ),
        const SizedBox(height: 8),
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(
            children: [
              for (final item in items) ...[
                _PillButton(
                  label: item.label,
                  selected: selected == item.value,
                  onTap: () => onSelected(item.value),
                ),
                const SizedBox(width: 8),
              ],
            ],
          ),
        ),
      ],
    );
  }
}

class _PillButton extends StatelessWidget {
  const _PillButton({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final bg = selected
        ? const Color(0xFFFFC815)
        : Colors.white.withValues(alpha: 0.78);
    final fg = selected ? Colors.white : const Color(0xFF1B1C1A);
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(999),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(999),
          border: Border.all(
            color: selected ? Colors.transparent : const Color(0xFFE4DED3),
          ),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: fg,
            fontWeight: FontWeight.w700,
            fontSize: 12,
          ),
        ),
      ),
    );
  }
}

class _AutobiographyHeader extends StatelessWidget {
  const _AutobiographyHeader({required this.years, required this.milestones});

  final List<Map<String, dynamic>> years;
  final List<Map<String, dynamic>> milestones;

  String _monthName(String key) {
    final month = int.tryParse(key.split('-').last) ?? 1;
    return const [
      'January',
      'February',
      'March',
      'April',
      'May',
      'June',
      'July',
      'August',
      'September',
      'October',
      'November',
      'December',
    ][month.clamp(1, 12) - 1];
  }

  @override
  Widget build(BuildContext context) {
    return _GlassPanel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Autobiography',
            style: TextStyle(
              fontFamily: 'Manrope',
              fontSize: 22,
              fontWeight: FontWeight.w900,
              color: Color(0xFFFFC815),
            ),
          ),
          const SizedBox(height: 6),
          Text(
            milestones.isEmpty
                ? 'AiPal will highlight milestones as your story grows.'
                : 'Milestones, wins, decisions, and project moments grouped into your life story.',
            style: const TextStyle(height: 1.45, color: Color(0xFF575C6B)),
          ),
          if (milestones.isNotEmpty) ...[
            const SizedBox(height: 14),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: milestones.take(6).map((item) {
                return Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 12,
                    vertical: 8,
                  ),
                  decoration: BoxDecoration(
                    color: const Color(0xFF003B2B).withValues(alpha: 0.10),
                    borderRadius: BorderRadius.circular(999),
                  ),
                  child: Text(
                    item['title']?.toString() ?? 'Milestone',
                    style: const TextStyle(
                      color: Color(0xFF003B2B),
                      fontWeight: FontWeight.w800,
                      fontSize: 12,
                    ),
                  ),
                );
              }).toList(),
            ),
          ],
          const SizedBox(height: 16),
          ...years.take(4).map((year) {
            final months = (year['months'] as List<dynamic>? ?? const [])
                .whereType<Map>()
                .map((item) => item.cast<String, dynamic>())
                .toList();
            return Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${year['year']} · ${year['item_count']} moments',
                    style: const TextStyle(
                      fontWeight: FontWeight.w900,
                      color: Color(0xFF1B1C1A),
                    ),
                  ),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: months.take(6).map((month) {
                      return Chip(
                        label: Text(
                          '${_monthName(month['month']?.toString() ?? '')} (${month['item_count']})',
                        ),
                        backgroundColor: Colors.white.withValues(alpha: 0.7),
                        side: const BorderSide(color: Color(0xFFE4DED3)),
                      );
                    }).toList(),
                  ),
                ],
              ),
            );
          }),
        ],
      ),
    );
  }
}

class _TimelineItemCard extends StatelessWidget {
  const _TimelineItemCard({required this.item, required this.isLast});

  final Map<String, dynamic> item;
  final bool isLast;

  String _dateLabel(dynamic value) {
    final dt = DateTime.tryParse(value?.toString() ?? '');
    if (dt == null) return 'Unknown date';
    final month = [
      'Jan',
      'Feb',
      'Mar',
      'Apr',
      'May',
      'Jun',
      'Jul',
      'Aug',
      'Sep',
      'Oct',
      'Nov',
      'Dec',
    ][dt.month - 1];
    return '$month ${dt.day}';
  }

  Color _sentimentColor(String? sentiment) {
    return switch (sentiment) {
      'positive' => const Color(0xFF003B2B),
      'negative' => const Color(0xFF8C2B3B),
      _ => const Color(0xFFFFC815),
    };
  }

  @override
  Widget build(BuildContext context) {
    final type = item['type']?.toString() ?? 'fact';
    final area = item['life_area']?.toString();
    final entities =
        (item['entities'] as List?)?.map((e) => e.toString()).toList() ??
        const [];
    final date = _dateLabel(item['date']);
    final sentiment = item['sentiment']?.toString();

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Column(
          children: [
            Container(
              width: 14,
              height: 14,
              decoration: BoxDecoration(
                color: _typeColor(type),
                shape: BoxShape.circle,
                boxShadow: [
                  BoxShadow(
                    color: _typeColor(type).withValues(alpha: 0.24),
                    blurRadius: 12,
                    spreadRadius: 2,
                  ),
                ],
              ),
            ),
            Container(
              width: 2,
              height: isLast ? 120 : 160,
              margin: const EdgeInsets.only(top: 6),
              color: const Color(0xFFD8D0C7),
            ),
          ],
        ),
        const SizedBox(width: 14),
        Expanded(
          child: _GlassPanel(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(
                        child: Text(
                          item['title']?.toString() ?? 'Memory',
                          style: const TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w800,
                            color: Color(0xFF1B1C1A),
                          ),
                        ),
                      ),
                      Text(
                        date,
                        style: const TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                          color: Color(0xFF575C6B),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      _Badge(
                        label: type.replaceAll('_', ' '),
                        color: _typeColor(type),
                      ),
                      if (area != null && area.isNotEmpty)
                        _Badge(
                          label: area.replaceAll('_', ' '),
                          color: const Color(0xFF003B2B),
                        ),
                      if (sentiment != null)
                        _Badge(
                          label: sentiment,
                          color: _sentimentColor(sentiment),
                        ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Text(
                    item['content']?.toString() ?? '',
                    style: const TextStyle(
                      fontSize: 14,
                      height: 1.55,
                      color: Color(0xFF30343F),
                    ),
                  ),
                  if (entities.isNotEmpty) ...[
                    const SizedBox(height: 12),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: entities
                          .take(4)
                          .map((entity) => _EntityChip(label: entity))
                          .toList(),
                    ),
                  ],
                  if ((item['follow_up_prompt']?.toString() ?? '')
                      .isNotEmpty) ...[
                    const SizedBox(height: 12),
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: const Color(0xFF003B2B).withValues(alpha: 0.08),
                        borderRadius: BorderRadius.circular(16),
                      ),
                      child: Text(
                        item['follow_up_prompt'].toString(),
                        style: const TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w600,
                          color: Color(0xFF003B2B),
                        ),
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }

  Color _typeColor(String type) {
    return switch (type) {
      'win' => const Color(0xFF003B2B),
      'important_event' => const Color(0xFFFFC815),
      'failure' || 'recurring_concern' => const Color(0xFF8C2B3B),
      'relationship' || 'person' => const Color(0xFF395C8A),
      _ => const Color(0xFFFFC815),
    };
  }
}

class _Badge extends StatelessWidget {
  const _Badge({required this.label, required this.color});

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withValues(alpha: 0.24)),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w700,
          color: color,
        ),
      ),
    );
  }
}

class _EntityChip extends StatelessWidget {
  const _EntityChip({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: const Color(0xFFF4F0E8),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        label,
        style: const TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w700,
          color: Color(0xFF4B444D),
        ),
      ),
    );
  }
}

class _EmptyTimelineState extends StatelessWidget {
  const _EmptyTimelineState();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.68),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: Colors.white.withValues(alpha: 0.78)),
      ),
      child: const Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'No timeline items yet',
            style: TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.w800,
              color: Color(0xFF1B1C1A),
            ),
          ),
          SizedBox(height: 8),
          Text(
            'As AiPal learns more about your wins, projects, events, and follow-ups, they will appear here.',
            style: TextStyle(
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

class _HeaderButton extends StatelessWidget {
  const _HeaderButton({required this.icon, required this.onTap});

  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(18),
      child: Container(
        width: 44,
        height: 44,
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.84),
          borderRadius: BorderRadius.circular(18),
          border: Border.all(color: Colors.white.withValues(alpha: 0.78)),
        ),
        child: Icon(icon, size: 20, color: const Color(0xFF1B1C1A)),
      ),
    );
  }
}
