import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/app_state.dart';
import 'goal_reflection_detail_screens.dart';

class GoalsScreen extends StatefulWidget {
  const GoalsScreen({super.key});

  @override
  State<GoalsScreen> createState() => _GoalsScreenState();
}

class _GoalsScreenState extends State<GoalsScreen> {
  Future<List<dynamic>>? _goalsFuture;

  @override
  void initState() {
    super.initState();
    _goalsFuture = _loadGoals();
  }

  Future<List<dynamic>> _loadGoals() =>
      context.read<AppState>().api.listGoals();

  Future<void> _refresh() async {
    if (!mounted) return;
    setState(() {
      _goalsFuture = _loadGoals();
    });
  }

  Future<void> _editGoal([Map<String, dynamic>? goal]) async {
    final api = context.read<AppState>().api;
    final titleController = TextEditingController(
      text: goal?['title']?.toString() ?? '',
    );
    final descriptionController = TextEditingController(
      text: goal?['description']?.toString() ?? '',
    );
    final lifeAreaController = TextEditingController(
      text: goal?['life_area']?.toString() ?? '',
    );
    final targetDateController = TextEditingController(
      text: goal?['target_date']?.toString().split('T').first ?? '',
    );
    var status = goal?['status']?.toString() ?? 'active';
    var priority = goal?['priority']?.toString() ?? 'medium';

    final result = await showModalBottomSheet<Map<String, dynamic>>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => StatefulBuilder(
        builder: (context, setSheetState) => _GoalEditorSheet(
          titleController: titleController,
          descriptionController: descriptionController,
          lifeAreaController: lifeAreaController,
          targetDateController: targetDateController,
          status: status,
          priority: priority,
          onStatusChanged: (v) => setSheetState(() => status = v),
          onPriorityChanged: (v) => setSheetState(() => priority = v),
        ),
      ),
    );

    titleController.dispose();
    descriptionController.dispose();
    lifeAreaController.dispose();
    targetDateController.dispose();

    if (result == null) return;
    if (goal == null) {
      await api.createGoal(result);
    } else {
      await api.updateGoal(goal['id'].toString(), result);
    }
    await _refresh();
  }

  Future<void> _deleteGoal(String id) async {
    final api = context.read<AppState>().api;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete goal?'),
        content: const Text('This removes the goal permanently.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (ok != true) return;
    await api.deleteGoal(id);
    await _refresh();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFFAF9F5),
      floatingActionButton: FloatingActionButton(
        onPressed: () => _editGoal(),
        backgroundColor: const Color(0xFFFFC815),
        foregroundColor: Colors.white,
        child: const Icon(Icons.add_rounded),
      ),
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 12, 20, 18),
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
                          'Goals',
                          style: TextStyle(
                            fontFamily: 'Manrope',
                            fontSize: 28,
                            fontWeight: FontWeight.w800,
                            color: Color(0xFF1B1C1A),
                          ),
                        ),
                        SizedBox(height: 2),
                        Text(
                          'Track what matters and keep your direction clear',
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
            Expanded(
              child: RefreshIndicator(
                onRefresh: _refresh,
                child: FutureBuilder<List<dynamic>>(
                  future: _goalsFuture,
                  builder: (context, snapshot) {
                    final goals = snapshot.data ?? const [];
                    if (snapshot.connectionState == ConnectionState.waiting) {
                      return const Center(child: CircularProgressIndicator());
                    }
                    return ListView(
                      padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
                      children: [
                        if (goals.isEmpty)
                          const _EmptyState()
                        else
                          ...goals.map(
                            (goal) => _GoalCard(
                              goal: goal.cast<String, dynamic>(),
                              onOpen: () => Navigator.of(context).push(
                                MaterialPageRoute(
                                  builder: (_) => GoalDetailScreen(
                                    goalId: goal['id'].toString(),
                                  ),
                                ),
                              ),
                              onEdit: () =>
                                  _editGoal(goal.cast<String, dynamic>()),
                              onDelete: () =>
                                  _deleteGoal(goal['id'].toString()),
                            ),
                          ),
                      ],
                    );
                  },
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _GoalCard extends StatelessWidget {
  const _GoalCard({
    required this.goal,
    required this.onOpen,
    required this.onEdit,
    required this.onDelete,
  });
  final Map<String, dynamic> goal;
  final VoidCallback onOpen;
  final VoidCallback onEdit;
  final VoidCallback onDelete;
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Material(
        color: Colors.white.withValues(alpha: 0.7),
        borderRadius: BorderRadius.circular(26),
        child: InkWell(
          borderRadius: BorderRadius.circular(26),
          onTap: onOpen,
          child: Padding(
            padding: const EdgeInsets.all(18),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        goal['title']?.toString() ?? 'Untitled goal',
                        style: const TextStyle(
                          fontFamily: 'Manrope',
                          fontSize: 18,
                          fontWeight: FontWeight.w800,
                          color: Color(0xFF1B1C1A),
                        ),
                      ),
                    ),
                    _Chip(label: goal['status']?.toString() ?? 'active'),
                  ],
                ),
                const SizedBox(height: 8),
                if ((goal['description']?.toString() ?? '').isNotEmpty)
                  Text(
                    goal['description'].toString(),
                    style: const TextStyle(
                      fontSize: 13.5,
                      height: 1.5,
                      color: Color(0xFF4B444D),
                    ),
                  ),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    if ((goal['life_area']?.toString() ?? '').isNotEmpty)
                      _Chip(label: goal['life_area'].toString()),
                    _Chip(label: goal['priority']?.toString() ?? 'medium'),
                    if ((goal['target_date']?.toString() ?? '').isNotEmpty)
                      _Chip(
                        label: goal['target_date'].toString().split('T').first,
                      ),
                  ],
                ),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 8,
                  children: [
                    OutlinedButton(
                      onPressed: onEdit,
                      child: const Text('Edit'),
                    ),
                    FilledButton.tonal(
                      onPressed: onDelete,
                      child: const Text('Delete'),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _GoalEditorSheet extends StatelessWidget {
  const _GoalEditorSheet({
    required this.titleController,
    required this.descriptionController,
    required this.lifeAreaController,
    required this.targetDateController,
    required this.status,
    required this.priority,
    required this.onStatusChanged,
    required this.onPriorityChanged,
  });

  final TextEditingController titleController;
  final TextEditingController descriptionController;
  final TextEditingController lifeAreaController;
  final TextEditingController targetDateController;
  final String status;
  final String priority;
  final ValueChanged<String> onStatusChanged;
  final ValueChanged<String> onPriorityChanged;

  @override
  Widget build(BuildContext context) {
    var localStatus = status;
    var localPriority = priority;
    return Padding(
      padding: EdgeInsets.only(
        bottom: MediaQuery.of(context).viewInsets.bottom + 16,
        left: 16,
        right: 16,
      ),
      child: Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: const Color(0xFFFAF9F5),
          borderRadius: BorderRadius.circular(30),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const _SheetHandle(),
            const SizedBox(height: 18),
            _Field(controller: titleController, label: 'Title'),
            const SizedBox(height: 12),
            _Field(
              controller: descriptionController,
              label: 'Description',
              maxLines: 4,
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: _Field(
                    controller: lifeAreaController,
                    label: 'Life area',
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: _Field(
                    controller: targetDateController,
                    label: 'Target date YYYY-MM-DD',
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: DropdownButtonFormField<String>(
                    initialValue: localStatus,
                    items: const [
                      DropdownMenuItem(value: 'active', child: Text('active')),
                      DropdownMenuItem(value: 'paused', child: Text('paused')),
                      DropdownMenuItem(value: 'done', child: Text('done')),
                    ],
                    onChanged: (v) {
                      final next = v ?? 'active';
                      localStatus = next;
                      onStatusChanged(next);
                    },
                    decoration: const InputDecoration(labelText: 'Status'),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: DropdownButtonFormField<String>(
                    initialValue: localPriority,
                    items: const [
                      DropdownMenuItem(value: 'low', child: Text('low')),
                      DropdownMenuItem(value: 'medium', child: Text('medium')),
                      DropdownMenuItem(value: 'high', child: Text('high')),
                    ],
                    onChanged: (v) {
                      final next = v ?? 'medium';
                      localPriority = next;
                      onPriorityChanged(next);
                    },
                    decoration: const InputDecoration(labelText: 'Priority'),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                onPressed: () {
                  Navigator.pop(context, {
                    'title': titleController.text.trim(),
                    'description': descriptionController.text.trim(),
                    'life_area': lifeAreaController.text.trim(),
                    'target_date': targetDateController.text.trim().isEmpty
                        ? null
                        : targetDateController.text.trim(),
                    'status': localStatus,
                    'priority': localPriority,
                  });
                },
                child: const Text('Save Goal'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Field extends StatelessWidget {
  const _Field({
    required this.controller,
    required this.label,
    this.maxLines = 1,
  });
  final TextEditingController controller;
  final String label;
  final int maxLines;
  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: controller,
      maxLines: maxLines,
      decoration: InputDecoration(labelText: label),
    );
  }
}

class _Chip extends StatelessWidget {
  const _Chip({required this.label});
  final String label;
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: const Color(0xFFF4F1EB),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        label,
        style: const TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w800,
          color: Color(0xFF1B1C1A),
        ),
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
    return Container(
      width: 48,
      height: 48,
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.75),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFFE6E1D6)),
      ),
      child: IconButton(
        icon: Icon(icon, color: const Color(0xFF1B1C1A)),
        onPressed: onTap,
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState();
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.6),
        borderRadius: BorderRadius.circular(24),
      ),
      child: const Text(
        'No goals yet. Create one to start linking your work and intentions.',
        style: TextStyle(fontSize: 14, height: 1.5, color: Color(0xFF4B444D)),
      ),
    );
  }
}

class _SheetHandle extends StatelessWidget {
  const _SheetHandle();
  @override
  Widget build(BuildContext context) {
    return Container(
      width: 48,
      height: 5,
      decoration: BoxDecoration(
        color: const Color(0xFFE8DFAF),
        borderRadius: BorderRadius.circular(999),
      ),
    );
  }
}
