import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/app_state.dart';
import 'home_shell.dart';

const _ivory = Color(0xFFFAF9F5);
const _brandGreen = Color(0xFF003B2B);
const _teal = Color(0xFF003B2B);

class KnowledgeGraphScreen extends StatefulWidget {
  const KnowledgeGraphScreen({super.key});

  @override
  State<KnowledgeGraphScreen> createState() => _KnowledgeGraphScreenState();
}

class _KnowledgeGraphScreenState extends State<KnowledgeGraphScreen> {
  final _searchController = TextEditingController();
  Future<Map<String, dynamic>>? _summaryFuture;
  Future<List<dynamic>>? _entitiesFuture;
  String? _filter;
  String _query = '';

  static const _filters = [
    'project',
    'person',
    'topic',
    'event',
    'relationship',
  ];

  @override
  void initState() {
    super.initState();
    _summaryFuture = _loadSummary();
    _entitiesFuture = _loadEntities();
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Future<Map<String, dynamic>> _loadSummary() =>
      context.read<AppState>().api.getKnowledgeSummary();

  Future<List<dynamic>> _loadEntities() {
    final api = context.read<AppState>().api;
    if (_query.isNotEmpty) {
      return api.searchKnowledge(_query, entityType: _filter);
    }
    return api.listKnowledgeEntities(entityType: _filter);
  }

  Future<void> _refresh() async {
    setState(() {
      _summaryFuture = _loadSummary();
      _entitiesFuture = _loadEntities();
    });
  }

  void _applyQuery(String value) {
    setState(() {
      _query = value.trim();
      _entitiesFuture = _loadEntities();
    });
  }

  void _applyFilter(String? filter) {
    setState(() {
      _filter = filter;
      _entitiesFuture = _loadEntities();
    });
  }

  Future<void> _openEntityDetail(Map<String, dynamic> entity) async {
    final graph = await context.read<AppState>().api.getKnowledgeGraph(
      entity['id'].toString(),
    );
    if (!mounted) return;
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _EntityDetailSheet(graph: graph),
    );
  }

  @override
  Widget build(BuildContext context) {
    return AiPalShellScaffold(
      title: 'Knowledge Graph',
      subtitle: 'People, projects, topics, and memories linked together',
      showDesktopSidebar: false,
      showMobileBottomNav: false,
      onNotificationsTap: () {},
      onProfileTap: () {},
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: FutureBuilder<Map<String, dynamic>>(
          future: _summaryFuture,
          builder: (context, summarySnapshot) {
            final summary = summarySnapshot.data ?? const <String, dynamic>{};
            final counts =
                summary['counts'] as Map<String, dynamic>? ?? const {};
            final entityTypes =
                counts['entity_types'] as Map<String, dynamic>? ?? const {};
            final patterns = summary['patterns'] as Map<String, dynamic>?;

            return FutureBuilder<List<dynamic>>(
              future: _entitiesFuture,
              builder: (context, entitiesSnapshot) {
                final entities = (entitiesSnapshot.data ?? const [])
                    .whereType<Map>()
                    .map((entity) => entity.cast<String, dynamic>())
                    .toList();

                return ListView(
                  padding: const EdgeInsets.fromLTRB(20, 20, 20, 96),
                  children: [
                    _HeroCard(
                      title: 'Your knowledge graph',
                      subtitle:
                          'A living map of the people, projects, and themes AiPal has picked up so far.',
                      stats: [
                        _Stat(
                          label: 'Entities',
                          value: counts['entities']?.toString() ?? '0',
                        ),
                        _Stat(
                          label: 'Edges',
                          value: counts['edges']?.toString() ?? '0',
                        ),
                        _Stat(
                          label: 'Memories',
                          value: counts['memories']?.toString() ?? '0',
                        ),
                      ],
                    ),
                    const SizedBox(height: 16),
                    Row(
                      children: [
                        Expanded(
                          child: _GlassPanel(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Text(
                                  'Projects',
                                  style: TextStyle(
                                    color: _brandGreen,
                                    fontSize: 16,
                                    fontWeight: FontWeight.w700,
                                  ),
                                ),
                                const SizedBox(height: 8),
                                Text(
                                  entityTypes['project']?.toString() ?? '0',
                                  style: const TextStyle(
                                    fontSize: 24,
                                    fontWeight: FontWeight.w800,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: _GlassPanel(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Text(
                                  'People',
                                  style: TextStyle(
                                    color: _teal,
                                    fontSize: 16,
                                    fontWeight: FontWeight.w700,
                                  ),
                                ),
                                const SizedBox(height: 8),
                                Text(
                                  entityTypes['person']?.toString() ?? '0',
                                  style: const TextStyle(
                                    fontSize: 24,
                                    fontWeight: FontWeight.w800,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        Expanded(
                          child: _GlassPanel(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Text(
                                  'Topics',
                                  style: TextStyle(
                                    color: _brandGreen,
                                    fontSize: 16,
                                    fontWeight: FontWeight.w700,
                                  ),
                                ),
                                const SizedBox(height: 8),
                                Text(
                                  entityTypes['topic']?.toString() ?? '0',
                                  style: const TextStyle(
                                    fontSize: 24,
                                    fontWeight: FontWeight.w800,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: _GlassPanel(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Text(
                                  'Relations',
                                  style: TextStyle(
                                    color: _teal,
                                    fontSize: 16,
                                    fontWeight: FontWeight.w700,
                                  ),
                                ),
                                const SizedBox(height: 8),
                                Text(
                                  counts['edges']?.toString() ?? '0',
                                  style: const TextStyle(
                                    fontSize: 24,
                                    fontWeight: FontWeight.w800,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 18),
                    _GlassPanel(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          TextField(
                            controller: _searchController,
                            onChanged: _applyQuery,
                            decoration: InputDecoration(
                              hintText: 'Search people, projects, or topics',
                              prefixIcon: const Icon(Icons.search_rounded),
                              filled: true,
                              fillColor: Colors.white.withValues(alpha: 0.78),
                              border: OutlineInputBorder(
                                borderRadius: BorderRadius.circular(18),
                                borderSide: BorderSide.none,
                              ),
                            ),
                          ),
                          const SizedBox(height: 12),
                          Wrap(
                            spacing: 10,
                            runSpacing: 10,
                            children: [
                              ChoiceChip(
                                label: const Text('All'),
                                selected: _filter == null,
                                onSelected: (_) => _applyFilter(null),
                              ),
                              ..._filters.map(
                                (filter) => ChoiceChip(
                                  label: Text(filter),
                                  selected: _filter == filter,
                                  onSelected: (_) => _applyFilter(filter),
                                ),
                              ),
                            ],
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 18),
                    if (patterns != null) ...[
                      _GlassPanel(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text(
                              'Graph patterns',
                              style: TextStyle(
                                color: _brandGreen,
                                fontSize: 18,
                                fontWeight: FontWeight.w800,
                              ),
                            ),
                            const SizedBox(height: 10),
                            ...(((patterns['patterns'] as List<dynamic>?) ??
                                    const [])
                                .map(
                                  (pattern) => Padding(
                                    padding: const EdgeInsets.only(bottom: 8),
                                    child: Text('• ${pattern.toString()}'),
                                  ),
                                )),
                          ],
                        ),
                      ),
                      const SizedBox(height: 18),
                    ],
                    _GlassPanel(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            entities.isEmpty ? 'No entities yet.' : 'Entities',
                            style: const TextStyle(
                              color: _brandGreen,
                              fontSize: 18,
                              fontWeight: FontWeight.w800,
                            ),
                          ),
                          const SizedBox(height: 12),
                          if (entities.isEmpty)
                            const Text(
                              'Approved memories will gradually build your graph here.',
                            ),
                          ...entities.map(
                            (entity) => Padding(
                              padding: const EdgeInsets.only(bottom: 10),
                              child: _EntityCard(
                                entity: entity,
                                onTap: () => _openEntityDetail(entity),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                );
              },
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
    required this.stats,
  });

  final String title;
  final String subtitle;
  final List<_Stat> stats;

  @override
  Widget build(BuildContext context) {
    return _GlassPanel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: const TextStyle(
              fontSize: 28,
              fontWeight: FontWeight.w800,
              color: _brandGreen,
            ),
          ),
          const SizedBox(height: 8),
          Text(subtitle, style: const TextStyle(color: Color(0xFF575C6B))),
          const SizedBox(height: 18),
          Wrap(
            spacing: 12,
            runSpacing: 12,
            children: stats
                .map(
                  (stat) => Container(
                    width: 98,
                    padding: const EdgeInsets.all(14),
                    decoration: BoxDecoration(
                      color: Colors.white.withValues(alpha: 0.72),
                      borderRadius: BorderRadius.circular(18),
                      border: Border.all(
                        color: Colors.white.withValues(alpha: 0.8),
                      ),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          stat.label,
                          style: const TextStyle(
                            fontSize: 12,
                            color: Color(0xFF5E6170),
                          ),
                        ),
                        const SizedBox(height: 8),
                        Text(
                          stat.value,
                          style: const TextStyle(
                            fontSize: 22,
                            fontWeight: FontWeight.w800,
                            color: _teal,
                          ),
                        ),
                      ],
                    ),
                  ),
                )
                .toList(),
          ),
        ],
      ),
    );
  }
}

class _Stat {
  const _Stat({required this.label, required this.value});
  final String label;
  final String value;
}

class _GlassPanel extends StatelessWidget {
  const _GlassPanel({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) => ClipRRect(
    borderRadius: BorderRadius.circular(24),
    child: BackdropFilter(
      filter: ImageFilter.blur(sigmaX: 18, sigmaY: 18),
      child: Container(
        padding: const EdgeInsets.all(18),
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.7),
          borderRadius: BorderRadius.circular(24),
          border: Border.all(color: Colors.white.withValues(alpha: 0.8)),
        ),
        child: child,
      ),
    ),
  );
}

class _EntityCard extends StatelessWidget {
  const _EntityCard({required this.entity, required this.onTap});

  final Map<String, dynamic> entity;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final type = entity['entity_type']?.toString() ?? 'topic';
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(20),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: const Color(0xFFF9F7F0),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: Colors.white.withValues(alpha: 0.9)),
        ),
        child: Row(
          children: [
            Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(
                color: type == 'project'
                    ? _brandGreen.withValues(alpha: 0.14)
                    : _teal.withValues(alpha: 0.14),
                borderRadius: BorderRadius.circular(14),
              ),
              child: Icon(
                type == 'person'
                    ? Icons.person_rounded
                    : type == 'project'
                    ? Icons.account_tree_rounded
                    : type == 'event'
                    ? Icons.event_rounded
                    : Icons.device_hub_rounded,
                color: type == 'project' ? _brandGreen : _teal,
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    entity['name']?.toString() ?? 'Untitled',
                    style: const TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    '${type.toUpperCase()} · ${(entity['confidence'] ?? 0).toString()} confidence',
                    style: const TextStyle(
                      fontSize: 12,
                      color: Color(0xFF686C79),
                    ),
                  ),
                ],
              ),
            ),
            const Icon(Icons.chevron_right_rounded, color: Color(0xFF8C8F98)),
          ],
        ),
      ),
    );
  }
}

class _EntityDetailSheet extends StatelessWidget {
  const _EntityDetailSheet({required this.graph});

  final Map<String, dynamic> graph;

  @override
  Widget build(BuildContext context) {
    final entity = graph['entity'] as Map<String, dynamic>? ?? const {};
    final relatedEntities =
        (graph['related_entities'] as List<dynamic>? ?? const [])
            .whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList();
    final relatedMemories =
        (graph['related_memories'] as List<dynamic>? ?? const [])
            .whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList();
    final edges = (graph['edges'] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((item) => item.cast<String, dynamic>())
        .toList();

    return SafeArea(
      child: Container(
        margin: const EdgeInsets.all(16),
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: _ivory,
          borderRadius: BorderRadius.circular(28),
          border: Border.all(color: Colors.white.withValues(alpha: 0.95)),
        ),
        child: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                entity['name']?.toString() ?? 'Entity',
                style: const TextStyle(
                  fontSize: 24,
                  fontWeight: FontWeight.w800,
                  color: _brandGreen,
                ),
              ),
              const SizedBox(height: 6),
              Text(
                entity['entity_type']?.toString() ?? '',
                style: const TextStyle(
                  color: _teal,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 16),
              _Section(
                title: 'Related memories',
                children: relatedMemories.isEmpty
                    ? [const Text('No related memories yet.')]
                    : relatedMemories
                          .map((memory) => _MemoryCard(memory: memory))
                          .toList(),
              ),
              const SizedBox(height: 14),
              _Section(
                title: 'Related entities',
                children: relatedEntities.isEmpty
                    ? [const Text('No related entities yet.')]
                    : relatedEntities
                          .map(
                            (related) => Padding(
                              padding: const EdgeInsets.only(bottom: 8),
                              child: Text(
                                '• ${related['name']?.toString() ?? ''}',
                              ),
                            ),
                          )
                          .toList(),
              ),
              const SizedBox(height: 14),
              _Section(
                title: 'Edges',
                children: edges.isEmpty
                    ? [const Text('No edges yet.')]
                    : edges
                          .map(
                            (edge) => Padding(
                              padding: const EdgeInsets.only(bottom: 8),
                              child: Text(
                                '• ${edge['relation_type']?.toString() ?? ''}',
                              ),
                            ),
                          )
                          .toList(),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Section extends StatelessWidget {
  const _Section({required this.title, required this.children});

  final String title;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.72),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: Colors.white.withValues(alpha: 0.8)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: const TextStyle(
              fontWeight: FontWeight.w800,
              color: _brandGreen,
            ),
          ),
          const SizedBox(height: 10),
          ...children,
        ],
      ),
    );
  }
}

class _MemoryCard extends StatelessWidget {
  const _MemoryCard({required this.memory});

  final Map<String, dynamic> memory;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFFF8F4EC),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            memory['title']?.toString() ?? '',
            style: const TextStyle(fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 4),
          Text(
            memory['content']?.toString() ?? '',
            maxLines: 3,
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ),
    );
  }
}
