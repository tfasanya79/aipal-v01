import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/app_state.dart';
import 'home_shell.dart';

const _brandGreen = Color(0xFF003B2B);
const _teal = Color(0xFF003B2B);
const _ivory = Color(0xFFFAF9F5);

class GrowthPlanScreen extends StatefulWidget {
  const GrowthPlanScreen({super.key});

  @override
  State<GrowthPlanScreen> createState() => _GrowthPlanScreenState();
}

class _GrowthPlanScreenState extends State<GrowthPlanScreen> {
  final _titleController = TextEditingController();
  String _horizon = '30_day';
  String? _goalId;
  Future<Map<String, dynamic>>? _future;
  Map<String, dynamic>? _result;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  @override
  void dispose() {
    _titleController.dispose();
    super.dispose();
  }

  Future<Map<String, dynamic>> _load() async {
    final api = context.read<AppState>().api;
    return {
      'goals': await api.listGoals(),
      'plans': await api.listGrowthPlans(),
    };
  }

  Future<void> _refresh() async {
    setState(() {
      _future = _load();
    });
  }

  Future<void> _create() async {
    final api = context.read<AppState>().api;
    final plan = await api.createGrowthPlan(
      goalId: _goalId,
      horizon: _horizon,
      title: _titleController.text.trim().isEmpty
          ? null
          : _titleController.text.trim(),
    );
    if (!mounted) return;
    setState(() {
      _result = plan;
      _future = _load();
    });
  }

  @override
  Widget build(BuildContext context) {
    return AiPalShellScaffold(
      title: 'Growth Plans',
      subtitle: 'Turn a goal into a 30/60/90-day path',
      showDesktopSidebar: false,
      showMobileBottomNav: false,
      onNotificationsTap: () {},
      onProfileTap: () {},
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: FutureBuilder<Map<String, dynamic>>(
          future: _future,
          builder: (context, snapshot) {
            final goals =
                (snapshot.data?['goals'] as List<dynamic>? ?? const [])
                    .whereType<Map>()
                    .map((item) => item.cast<String, dynamic>())
                    .toList();
            final plans =
                (snapshot.data?['plans'] as List<dynamic>? ?? const [])
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
                        'Build a 30/60/90-day plan',
                        style: TextStyle(
                          fontSize: 28,
                          fontWeight: FontWeight.w800,
                          color: _brandGreen,
                        ),
                      ),
                      const SizedBox(height: 8),
                      const Text(
                        'Give AiPal a goal and it will break it into milestones, weekly focus, risks, and success metrics.',
                      ),
                      const SizedBox(height: 16),
                      TextField(
                        controller: _titleController,
                        decoration: const InputDecoration(
                          labelText: 'Plan title (optional)',
                        ),
                      ),
                      const SizedBox(height: 12),
                      DropdownButtonFormField<String?>(
                        initialValue: _goalId,
                        decoration: const InputDecoration(
                          labelText: 'Link to goal (optional)',
                        ),
                        items: [
                          const DropdownMenuItem<String?>(
                            value: null,
                            child: Text('No goal selected'),
                          ),
                          ...goals.map(
                            (goal) => DropdownMenuItem<String?>(
                              value: goal['id']?.toString(),
                              child: Text(goal['title']?.toString() ?? ''),
                            ),
                          ),
                        ],
                        onChanged: (value) => setState(() => _goalId = value),
                      ),
                      const SizedBox(height: 12),
                      DropdownButtonFormField<String>(
                        initialValue: _horizon,
                        decoration: const InputDecoration(labelText: 'Horizon'),
                        items: const [
                          DropdownMenuItem(
                            value: '30_day',
                            child: Text('30 day'),
                          ),
                          DropdownMenuItem(
                            value: '60_day',
                            child: Text('60 day'),
                          ),
                          DropdownMenuItem(
                            value: '90_day',
                            child: Text('90 day'),
                          ),
                        ],
                        onChanged: (value) =>
                            setState(() => _horizon = value ?? '30_day'),
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
                          child: const Text('Create plan'),
                        ),
                      ),
                    ],
                  ),
                ),
                if (_result != null) ...[
                  const SizedBox(height: 16),
                  _PlanCard(plan: _result!),
                ],
                const SizedBox(height: 16),
                _GlassPanel(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'Existing plans',
                        style: TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.w700,
                          color: _brandGreen,
                        ),
                      ),
                      const SizedBox(height: 12),
                      if (plans.isEmpty)
                        const Text('No growth plans yet.')
                      else
                        Column(
                          children: plans
                              .take(6)
                              .map(
                                (plan) => Padding(
                                  padding: const EdgeInsets.only(bottom: 10),
                                  child: _PlanRow(plan: plan),
                                ),
                              )
                              .toList(),
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

class _PlanCard extends StatelessWidget {
  const _PlanCard({required this.plan});
  final Map<String, dynamic> plan;

  @override
  Widget build(BuildContext context) => _GlassPanel(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          plan['title']?.toString() ?? '',
          style: const TextStyle(
            fontSize: 18,
            fontWeight: FontWeight.w700,
            color: _brandGreen,
          ),
        ),
        const SizedBox(height: 8),
        Text(plan['summary']?.toString() ?? ''),
        const SizedBox(height: 10),
        Text(
          'Horizon: ${plan['horizon']?.toString() ?? ''}',
          style: const TextStyle(color: _teal),
        ),
      ],
    ),
  );
}

class _PlanRow extends StatelessWidget {
  const _PlanRow({required this.plan});
  final Map<String, dynamic> plan;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(14),
    decoration: BoxDecoration(
      color: _ivory,
      borderRadius: BorderRadius.circular(18),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          plan['title']?.toString() ?? '',
          style: const TextStyle(
            fontWeight: FontWeight.w700,
            color: _brandGreen,
          ),
        ),
        const SizedBox(height: 4),
        Text(plan['summary']?.toString() ?? ''),
      ],
    ),
  );
}
