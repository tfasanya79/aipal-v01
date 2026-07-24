import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/app_state.dart';

class PlannerScreen extends StatefulWidget {
  const PlannerScreen({super.key});

  @override
  State<PlannerScreen> createState() => _PlannerScreenState();
}

class _PlannerScreenState extends State<PlannerScreen> {
  String _selected = 'daily';
  Map<String, dynamic>? _draft;
  bool _busy = false;

  Future<void> _generate() async {
    setState(() => _busy = true);
    try {
      final draft = await context.read<AppState>().api.generatePlannerDraft(
        _selected,
      );
      if (mounted) setState(() => _draft = draft);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _confirm() async {
    setState(() => _busy = true);
    try {
      final state = context.read<AppState>();
      await state.api.confirmPlannerDraft();
      await state.refreshTodayView();
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('Plan added to Today.')));
      setState(() => _draft = null);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final tasks = (_draft?['proposed_tasks'] as List? ?? [])
        .whereType<Map>()
        .map((item) => item.cast<String, dynamic>())
        .toList();
    return Scaffold(
      backgroundColor: const Color(0xFFFAF9F5),
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        foregroundColor: const Color(0xFF1B1C1A),
        title: const Text('Planner Engine'),
      ),
      body: Stack(
        children: [
          const _PlannerAtmosphere(),
          ListView(
            padding: const EdgeInsets.fromLTRB(20, 18, 20, 40),
            children: [
              const Text(
                'Build a realistic draft first. Confirm only when it feels right.',
                style: TextStyle(
                  color: Color(0xFF4B444D),
                  fontSize: 16,
                  height: 1.5,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 18),
              Wrap(
                spacing: 10,
                runSpacing: 10,
                children:
                    const [
                      _PlanChoice(id: 'daily', label: 'Daily'),
                      _PlanChoice(id: 'weekly', label: 'Weekly'),
                      _PlanChoice(id: 'monthly', label: 'Monthly'),
                      _PlanChoice(id: 'quarterly', label: 'Quarterly'),
                      _PlanChoice(id: '90-day', label: '90-day'),
                      _PlanChoice(id: 'life-roadmap', label: 'Life Roadmap'),
                    ].map((choice) {
                      return ChoiceChip(
                        label: Text(choice.label),
                        selected: _selected == choice.id,
                        selectedColor: const Color(
                          0xFFFFC815,
                        ).withValues(alpha: 0.16),
                        labelStyle: TextStyle(
                          color: _selected == choice.id
                              ? const Color(0xFFFFC815)
                              : const Color(0xFF4B444D),
                          fontWeight: FontWeight.w800,
                        ),
                        onSelected: (_) =>
                            setState(() => _selected = choice.id),
                      );
                    }).toList(),
              ),
              const SizedBox(height: 18),
              FilledButton.icon(
                onPressed: _busy ? null : _generate,
                icon: _busy
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.auto_awesome_rounded),
                label: const Text('Generate Draft'),
                style: FilledButton.styleFrom(
                  backgroundColor: const Color(0xFFFFC815),
                  foregroundColor: Colors.white,
                  minimumSize: const Size.fromHeight(52),
                ),
              ),
              const SizedBox(height: 24),
              if (_draft == null)
                const _PlannerEmpty()
              else
                _DraftPanel(
                  intent: _draft?['intent']?.toString() ?? 'plan',
                  tasks: tasks,
                  busy: _busy,
                  onConfirm: _confirm,
                ),
            ],
          ),
        ],
      ),
    );
  }
}

class _PlanChoice {
  const _PlanChoice({required this.id, required this.label});
  final String id;
  final String label;
}

class _DraftPanel extends StatelessWidget {
  const _DraftPanel({
    required this.intent,
    required this.tasks,
    required this.busy,
    required this.onConfirm,
  });

  final String intent;
  final List<Map<String, dynamic>> tasks;
  final bool busy;
  final VoidCallback onConfirm;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.62),
        borderRadius: BorderRadius.circular(30),
        border: Border.all(color: Colors.white.withValues(alpha: 0.9)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            intent.replaceAll('_', ' ').toUpperCase(),
            style: const TextStyle(
              color: Color(0xFF003B2B),
              fontSize: 12,
              fontWeight: FontWeight.w900,
              letterSpacing: 1.1,
            ),
          ),
          const SizedBox(height: 14),
          ...tasks.map((task) => _DraftTaskTile(task: task)),
          const SizedBox(height: 12),
          FilledButton.icon(
            onPressed: busy ? null : onConfirm,
            icon: const Icon(Icons.check_rounded),
            label: const Text('Confirm and add to Today'),
            style: FilledButton.styleFrom(
              backgroundColor: const Color(0xFF003B2B),
              foregroundColor: Colors.white,
              minimumSize: const Size.fromHeight(50),
            ),
          ),
        ],
      ),
    );
  }
}

class _DraftTaskTile extends StatelessWidget {
  const _DraftTaskTile({required this.task});

  final Map<String, dynamic> task;

  @override
  Widget build(BuildContext context) {
    final title = task['title']?.toString() ?? 'Draft item';
    final minutes = task['estimated_minutes']?.toString() ?? '30';
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFFFAF9F5).withValues(alpha: 0.76),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: const Color(0xFFE6E1D6)),
      ),
      child: Row(
        children: [
          const Icon(Icons.view_timeline_rounded, color: Color(0xFFFFC815)),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              title,
              style: const TextStyle(
                color: Color(0xFF1B1C1A),
                fontWeight: FontWeight.w800,
                height: 1.35,
              ),
            ),
          ),
          Text(
            '$minutes min',
            style: const TextStyle(
              color: Color(0xFF4B444D),
              fontWeight: FontWeight.w700,
            ),
          ),
        ],
      ),
    );
  }
}

class _PlannerEmpty extends StatelessWidget {
  const _PlannerEmpty();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(22),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.54),
        borderRadius: BorderRadius.circular(28),
        border: Border.all(color: Colors.white.withValues(alpha: 0.9)),
      ),
      child: const Text(
        'Choose a planning horizon and AiPal will draft something balanced before anything is added to Today.',
        style: TextStyle(
          color: Color(0xFF4B444D),
          fontSize: 15,
          height: 1.5,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}

class _PlannerAtmosphere extends StatelessWidget {
  const _PlannerAtmosphere();

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: DecoratedBox(
        decoration: BoxDecoration(
          gradient: RadialGradient(
            center: Alignment.topRight,
            radius: 1.1,
            colors: [
              const Color(0xFF003B2B).withValues(alpha: 0.16),
              const Color(0xFFFAF9F5).withValues(alpha: 0),
            ],
          ),
        ),
        child: const SizedBox.expand(),
      ),
    );
  }
}
