import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/app_state.dart';
import 'home_shell.dart';

const _brandGreen = Color(0xFF003B2B);
const _teal = Color(0xFF003B2B);
const _ivory = Color(0xFFFAF9F5);

class CoachScreen extends StatefulWidget {
  const CoachScreen({super.key});

  @override
  State<CoachScreen> createState() => _CoachScreenState();
}

class _CoachScreenState extends State<CoachScreen> {
  final _questionController = TextEditingController();
  final _optionsController = TextEditingController();
  Future<Map<String, dynamic>>? _future;
  Map<String, dynamic>? _result;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  @override
  void dispose() {
    _questionController.dispose();
    _optionsController.dispose();
    super.dispose();
  }

  Future<Map<String, dynamic>> _load() async {
    final api = context.read<AppState>().api;
    return {
      'decisions': await api.listCoachingDecisions(),
      'frameworks': await api.listFrameworks(),
    };
  }

  Future<void> _refresh() async {
    setState(() {
      _future = _load();
    });
  }

  Future<void> _analyze() async {
    final question = _questionController.text.trim();
    if (question.isEmpty) return;
    final options = _optionsController.text
        .split(RegExp(r'[\n,]'))
        .map((item) => item.trim())
        .where((item) => item.isNotEmpty)
        .toList();
    final api = context.read<AppState>().api;
    final result = await api.coachDecision(
      question,
      options: options.isEmpty ? null : options,
    );
    if (!mounted) return;
    setState(() {
      _result = result;
      _future = _load();
    });
  }

  @override
  Widget build(BuildContext context) {
    return AiPalShellScaffold(
      title: 'Coach',
      subtitle: 'Decision coaching, frameworks, and next-step thinking',
      showDesktopSidebar: false,
      showMobileBottomNav: false,
      onNotificationsTap: () {},
      onProfileTap: () {},
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: FutureBuilder<Map<String, dynamic>>(
          future: _future,
          builder: (context, snapshot) {
            final data = snapshot.data;
            final frameworks =
                (data?['frameworks'] as List<dynamic>? ?? const []);
            final decisions = (data?['decisions'] as List<dynamic>? ?? const [])
                .whereType<Map>()
                .map((item) => item.cast<String, dynamic>())
                .toList();

            return ListView(
              padding: const EdgeInsets.fromLTRB(20, 24, 20, 96),
              children: [
                _GlassPanel(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'Thinking mode for hard choices.',
                        style: TextStyle(
                          fontFamily: 'Manrope',
                          fontSize: 28,
                          height: 1.1,
                          fontWeight: FontWeight.w800,
                          color: _brandGreen,
                        ),
                      ),
                      const SizedBox(height: 8),
                      const Text(
                        'Ask about tradeoffs, strategy, or what to do next. AiPal will choose a thinking framework and help you reason clearly.',
                        style: TextStyle(color: Color(0xFF575C6B)),
                      ),
                      const SizedBox(height: 20),
                      TextField(
                        controller: _questionController,
                        minLines: 2,
                        maxLines: 4,
                        decoration: const InputDecoration(
                          labelText: 'Decision or strategy question',
                        ),
                      ),
                      const SizedBox(height: 12),
                      TextField(
                        controller: _optionsController,
                        minLines: 1,
                        maxLines: 3,
                        decoration: const InputDecoration(
                          labelText: 'Options, separated by commas or lines',
                        ),
                      ),
                      const SizedBox(height: 16),
                      Align(
                        alignment: Alignment.centerRight,
                        child: FilledButton(
                          style: FilledButton.styleFrom(
                            backgroundColor: _teal,
                            foregroundColor: Colors.white,
                          ),
                          onPressed: _analyze,
                          child: const Text('Analyze decision'),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 16),
                if (_result != null) ...[
                  _ResultCard(result: _result!),
                  const SizedBox(height: 16),
                ],
                _GlassPanel(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'Thinking frameworks',
                        style: TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.w700,
                          color: _brandGreen,
                        ),
                      ),
                      const SizedBox(height: 12),
                      Wrap(
                        spacing: 10,
                        runSpacing: 10,
                        children: frameworks
                            .whereType<Map>()
                            .map((item) => item.cast<String, dynamic>())
                            .map(
                              (framework) => _FrameworkChip(
                                name: framework['name']?.toString() ?? '',
                                description:
                                    framework['description']?.toString() ?? '',
                              ),
                            )
                            .toList(),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 16),
                _GlassPanel(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'Recent decisions',
                        style: TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.w700,
                          color: _brandGreen,
                        ),
                      ),
                      const SizedBox(height: 12),
                      if (decisions.isEmpty)
                        const Text('No decisions yet.')
                      else
                        Column(
                          children: decisions.take(6).map((decision) {
                            return Padding(
                              padding: const EdgeInsets.only(bottom: 10),
                              child: _DecisionTile(decision: decision),
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
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.72),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: Colors.white.withValues(alpha: 0.75)),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF1A1F2C).withValues(alpha: 0.06),
            blurRadius: 24,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: child,
    );
  }
}

class _ResultCard extends StatelessWidget {
  const _ResultCard({required this.result});

  final Map<String, dynamic> result;

  @override
  Widget build(BuildContext context) {
    final analysis = result['analysis'] as Map<String, dynamic>? ?? const {};
    final matrix = (analysis['matrix'] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((item) => item.cast<String, dynamic>())
        .toList();
    final recommendation = result['recommendation']?.toString() ?? '';
    final framework = result['framework']?.toString() ?? '';
    final confidence = result['confidence'];

    return _GlassPanel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Coach analysis',
            style: TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.w700,
              color: _brandGreen,
            ),
          ),
          const SizedBox(height: 10),
          Text(
            framework.replaceAll('_', ' ').toUpperCase(),
            style: const TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w700,
              color: _teal,
              letterSpacing: 0.4,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            recommendation,
            style: const TextStyle(fontSize: 16, height: 1.4),
          ),
          if (confidence != null) ...[
            const SizedBox(height: 8),
            Text(
              'Confidence ${(confidence as num).toStringAsFixed(2)}',
              style: const TextStyle(fontSize: 12, color: Color(0xFF575C6B)),
            ),
          ],
          if (matrix.isNotEmpty) ...[
            const SizedBox(height: 14),
            ...matrix
                .take(3)
                .map(
                  (entry) => Padding(
                    padding: const EdgeInsets.only(bottom: 10),
                    child: Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: _ivory,
                        borderRadius: BorderRadius.circular(16),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            entry['option']?.toString() ?? '',
                            style: const TextStyle(
                              fontWeight: FontWeight.w700,
                              color: _brandGreen,
                            ),
                          ),
                          const SizedBox(height: 4),
                          Text('Score ${entry['score']?.toString() ?? ''}'),
                        ],
                      ),
                    ),
                  ),
                ),
          ],
        ],
      ),
    );
  }
}

class _FrameworkChip extends StatelessWidget {
  const _FrameworkChip({required this.name, required this.description});

  final String name;
  final String description;

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: description,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: const Color(0xFFEDE8F1),
          borderRadius: BorderRadius.circular(999),
        ),
        child: Text(
          name.replaceAll('_', ' '),
          style: const TextStyle(
            fontSize: 12,
            fontWeight: FontWeight.w700,
            color: _brandGreen,
          ),
        ),
      ),
    );
  }
}

class _DecisionTile extends StatelessWidget {
  const _DecisionTile({required this.decision});

  final Map<String, dynamic> decision;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: _ivory,
        borderRadius: BorderRadius.circular(18),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            decision['title']?.toString() ?? '',
            style: const TextStyle(
              fontWeight: FontWeight.w700,
              color: _brandGreen,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            decision['recommendation']?.toString() ?? '',
            style: const TextStyle(height: 1.4),
          ),
        ],
      ),
    );
  }
}
