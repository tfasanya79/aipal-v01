import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/app_state.dart';
import 'task_detail_screen.dart';

class GoalDetailScreen extends StatefulWidget {
  const GoalDetailScreen({super.key, required this.goalId});

  final String goalId;

  @override
  State<GoalDetailScreen> createState() => _GoalDetailScreenState();
}

class _GoalDetailScreenState extends State<GoalDetailScreen> {
  Future<Map<String, dynamic>>? _detailFuture;

  @override
  void initState() {
    super.initState();
    _detailFuture = _load();
  }

  Future<Map<String, dynamic>> _load() =>
      context.read<AppState>().api.getGoalDetail(widget.goalId);

  Future<void> _refresh() async {
    if (!mounted) return;
    setState(() {
      _detailFuture = _load();
    });
  }

  Future<void> _addLinkedTask(Map<String, dynamic> goal) async {
    final api = context.read<AppState>().api;
    final titleController = TextEditingController();
    final notesController = TextEditingController();

    final result = await showModalBottomSheet<Map<String, String>>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => _QuickTaskSheet(
        titleController: titleController,
        notesController: notesController,
      ),
    );

    titleController.dispose();
    notesController.dispose();

    if (result == null) return;
    final title = result['title']?.trim() ?? '';
    if (title.isEmpty) return;

    await api.createTask(
      title,
      notes: result['notes'],
      goalId: goal['id'].toString(),
    );
    await _refresh();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFFAF9F5),
      body: SafeArea(
        child: FutureBuilder<Map<String, dynamic>>(
          future: _detailFuture,
          builder: (context, snapshot) {
            final data = snapshot.data;
            final goal = (data?['goal'] as Map?)?.cast<String, dynamic>();
            final tasks =
                (data?['linked_tasks'] as List?)
                    ?.cast<Map<String, dynamic>>() ??
                [];
            final reflections =
                (data?['linked_reflections'] as List?)
                    ?.cast<Map<String, dynamic>>() ??
                [];

            return Column(
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
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              goal?['title']?.toString() ?? 'Goal detail',
                              style: const TextStyle(
                                fontFamily: 'Manrope',
                                fontSize: 28,
                                fontWeight: FontWeight.w800,
                                color: Color(0xFF1B1C1A),
                              ),
                            ),
                            const SizedBox(height: 2),
                            const Text(
                              'Linked tasks and reflections',
                              style: TextStyle(
                                fontSize: 13,
                                color: Color(0xFF575C6B),
                              ),
                            ),
                          ],
                        ),
                      ),
                      IconButton(
                        onPressed: () => _refresh(),
                        icon: const Icon(Icons.refresh_rounded),
                      ),
                    ],
                  ),
                ),
                Expanded(
                  child: RefreshIndicator(
                    onRefresh: _refresh,
                    child: ListView(
                      padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
                      children: [
                        if (snapshot.connectionState ==
                                ConnectionState.waiting &&
                            goal == null)
                          const Padding(
                            padding: EdgeInsets.symmetric(vertical: 80),
                            child: Center(child: CircularProgressIndicator()),
                          )
                        else ...[
                          _DetailCard(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Wrap(
                                  spacing: 8,
                                  runSpacing: 8,
                                  children: [
                                    _Chip(
                                      label:
                                          goal?['status']?.toString() ??
                                          'active',
                                    ),
                                    if ((goal?['life_area']?.toString() ?? '')
                                        .isNotEmpty)
                                      _Chip(
                                        label: goal!['life_area'].toString(),
                                      ),
                                    _Chip(
                                      label:
                                          goal?['priority']?.toString() ??
                                          'medium',
                                    ),
                                    if ((goal?['target_date']?.toString() ?? '')
                                        .isNotEmpty)
                                      _Chip(
                                        label: goal!['target_date']
                                            .toString()
                                            .split('T')
                                            .first,
                                      ),
                                  ],
                                ),
                                const SizedBox(height: 14),
                                Text(
                                  goal?['description']?.toString().isNotEmpty ==
                                          true
                                      ? goal!['description'].toString()
                                      : 'No description added yet.',
                                  style: const TextStyle(
                                    fontSize: 14,
                                    height: 1.5,
                                    color: Color(0xFF4B444D),
                                  ),
                                ),
                                const SizedBox(height: 14),
                                Wrap(
                                  spacing: 10,
                                  runSpacing: 10,
                                  children: [
                                    FilledButton.icon(
                                      onPressed: goal == null
                                          ? null
                                          : () => _addLinkedTask(goal),
                                      icon: const Icon(
                                        Icons.add_task_rounded,
                                        size: 18,
                                      ),
                                      label: const Text('Add linked task'),
                                    ),
                                    OutlinedButton.icon(
                                      onPressed: () => _refresh(),
                                      icon: const Icon(
                                        Icons.sync_rounded,
                                        size: 18,
                                      ),
                                      label: const Text('Refresh'),
                                    ),
                                  ],
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(height: 18),
                          _SectionTitle(
                            title: 'Linked tasks',
                            count: tasks.length,
                          ),
                          const SizedBox(height: 12),
                          if (tasks.isEmpty)
                            const _EmptyCard(
                              text: 'No tasks are linked to this goal yet.',
                            )
                          else
                            ...tasks.map(
                              (task) => _LinkedTaskCard(
                                task: task,
                                onTap: () {
                                  Navigator.of(context).push(
                                    MaterialPageRoute(
                                      builder: (_) => TaskDetailScreen(
                                        taskId: task['id'].toString(),
                                      ),
                                    ),
                                  );
                                },
                              ),
                            ),
                          const SizedBox(height: 18),
                          _SectionTitle(
                            title: 'Linked reflections',
                            count: reflections.length,
                          ),
                          const SizedBox(height: 12),
                          if (reflections.isEmpty)
                            const _EmptyCard(
                              text:
                                  'No reflections are linked to this goal yet.',
                            )
                          else
                            ...reflections.map(
                              (reflection) => _LinkedReflectionCard(
                                reflection: reflection,
                                onTap: () {
                                  Navigator.of(context).push(
                                    MaterialPageRoute(
                                      builder: (_) => ReflectionDetailScreen(
                                        reflectionId: reflection['id']
                                            .toString(),
                                      ),
                                    ),
                                  );
                                },
                              ),
                            ),
                        ],
                      ],
                    ),
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

class ReflectionDetailScreen extends StatefulWidget {
  const ReflectionDetailScreen({super.key, required this.reflectionId});

  final String reflectionId;

  @override
  State<ReflectionDetailScreen> createState() => _ReflectionDetailScreenState();
}

class _ReflectionDetailScreenState extends State<ReflectionDetailScreen> {
  Future<Map<String, dynamic>>? _detailFuture;

  @override
  void initState() {
    super.initState();
    _detailFuture = _load();
  }

  Future<Map<String, dynamic>> _load() =>
      context.read<AppState>().api.getReflectionDetail(widget.reflectionId);

  Future<void> _refresh() async {
    if (!mounted) return;
    setState(() {
      _detailFuture = _load();
    });
  }

  Future<void> _linkGoal(Map<String, dynamic>? current) async {
    final api = context.read<AppState>().api;
    final goals = await api.listGoals();
    if (!mounted) return;

    final selected = await showModalBottomSheet<String?>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => _GoalPickerSheet(
        goals: goals.cast<Map<String, dynamic>>(),
        currentGoalId: current?['goal_id']?.toString(),
      ),
    );

    if (selected == null) return;
    await api.updateReflection(widget.reflectionId, {'goal_id': selected});
    await _refresh();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFFAF9F5),
      body: SafeArea(
        child: FutureBuilder<Map<String, dynamic>>(
          future: _detailFuture,
          builder: (context, snapshot) {
            final data = snapshot.data;
            final reflection = (data?['reflection'] as Map?)
                ?.cast<String, dynamic>();
            final goal = (data?['linked_goal'] as Map?)
                ?.cast<String, dynamic>();

            return Column(
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
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              '${reflection?['type']?.toString().toUpperCase() ?? 'DAILY'} REFLECTION',
                              style: const TextStyle(
                                fontFamily: 'Manrope',
                                fontSize: 28,
                                fontWeight: FontWeight.w800,
                                color: Color(0xFF1B1C1A),
                              ),
                            ),
                            const SizedBox(height: 2),
                            const Text(
                              'Wins, challenges, lessons, and mood',
                              style: TextStyle(
                                fontSize: 13,
                                color: Color(0xFF575C6B),
                              ),
                            ),
                          ],
                        ),
                      ),
                      IconButton(
                        onPressed: () => _refresh(),
                        icon: const Icon(Icons.refresh_rounded),
                      ),
                    ],
                  ),
                ),
                Expanded(
                  child: RefreshIndicator(
                    onRefresh: _refresh,
                    child: ListView(
                      padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
                      children: [
                        if (snapshot.connectionState ==
                                ConnectionState.waiting &&
                            reflection == null)
                          const Padding(
                            padding: EdgeInsets.symmetric(vertical: 80),
                            child: Center(child: CircularProgressIndicator()),
                          )
                        else ...[
                          _DetailCard(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Wrap(
                                  spacing: 8,
                                  runSpacing: 8,
                                  children: [
                                    _Chip(
                                      label:
                                          reflection?['mood']?.toString() ??
                                          'neutral',
                                    ),
                                    if (goal != null)
                                      _Chip(
                                        label:
                                            goal['title']?.toString() ??
                                            'Linked goal',
                                      ),
                                  ],
                                ),
                                const SizedBox(height: 14),
                                if ((reflection?['wins']?.toString() ?? '')
                                    .isNotEmpty)
                                  _Block(
                                    label: 'Wins',
                                    value: reflection!['wins'].toString(),
                                  ),
                                if ((reflection?['challenges']?.toString() ??
                                        '')
                                    .isNotEmpty)
                                  _Block(
                                    label: 'Challenges',
                                    value: reflection!['challenges'].toString(),
                                  ),
                                if ((reflection?['lessons']?.toString() ?? '')
                                    .isNotEmpty)
                                  _Block(
                                    label: 'Lessons',
                                    value: reflection!['lessons'].toString(),
                                  ),
                                if ((reflection?['wins']?.toString() ?? '')
                                        .isEmpty &&
                                    (reflection?['challenges']?.toString() ??
                                            '')
                                        .isEmpty &&
                                    (reflection?['lessons']?.toString() ?? '')
                                        .isEmpty)
                                  const Text(
                                    'No reflection notes were added yet.',
                                    style: TextStyle(
                                      fontSize: 14,
                                      height: 1.5,
                                      color: Color(0xFF4B444D),
                                    ),
                                  ),
                                const SizedBox(height: 14),
                                Wrap(
                                  spacing: 10,
                                  runSpacing: 10,
                                  children: [
                                    FilledButton.icon(
                                      onPressed: () => _linkGoal(reflection),
                                      icon: const Icon(
                                        Icons.flag_rounded,
                                        size: 18,
                                      ),
                                      label: const Text('Link to goal'),
                                    ),
                                    if (goal != null)
                                      OutlinedButton.icon(
                                        onPressed: () {
                                          Navigator.of(context).push(
                                            MaterialPageRoute(
                                              builder: (_) => GoalDetailScreen(
                                                goalId: goal['id'].toString(),
                                              ),
                                            ),
                                          );
                                        },
                                        icon: const Icon(
                                          Icons.open_in_new_rounded,
                                          size: 18,
                                        ),
                                        label: const Text('Open goal'),
                                      ),
                                  ],
                                ),
                              ],
                            ),
                          ),
                        ],
                      ],
                    ),
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

class _QuickTaskSheet extends StatelessWidget {
  const _QuickTaskSheet({
    required this.titleController,
    required this.notesController,
  });

  final TextEditingController titleController;
  final TextEditingController notesController;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        left: 16,
        right: 16,
        bottom: MediaQuery.of(context).viewInsets.bottom + 16,
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
            _Field(controller: titleController, label: 'Task title'),
            const SizedBox(height: 12),
            _Field(controller: notesController, label: 'Notes', maxLines: 3),
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                onPressed: () {
                  Navigator.pop(context, {
                    'title': titleController.text.trim(),
                    'notes': notesController.text.trim(),
                  });
                },
                child: const Text('Add Task'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _GoalPickerSheet extends StatelessWidget {
  const _GoalPickerSheet({required this.goals, required this.currentGoalId});

  final List<Map<String, dynamic>> goals;
  final String? currentGoalId;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        left: 16,
        right: 16,
        bottom: MediaQuery.of(context).viewInsets.bottom + 16,
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
            const Align(
              alignment: Alignment.centerLeft,
              child: Text(
                'Link reflection to goal',
                style: TextStyle(
                  fontFamily: 'Manrope',
                  fontSize: 22,
                  fontWeight: FontWeight.w800,
                  color: Color(0xFF1B1C1A),
                ),
              ),
            ),
            const SizedBox(height: 12),
            if (currentGoalId != null)
              _GoalLinkOption(
                label: 'Unlink from goal',
                subtitle: 'Keep the reflection without a linked goal.',
                icon: Icons.link_off_rounded,
                onTap: () => Navigator.pop(context, ''),
              ),
            ...goals.map(
              (goal) => _GoalLinkOption(
                label: goal['title']?.toString() ?? 'Untitled goal',
                subtitle: goal['life_area']?.toString() ?? 'Goal',
                icon: Icons.flag_rounded,
                selected: goal['id']?.toString() == currentGoalId,
                onTap: () => Navigator.pop(context, goal['id'].toString()),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _GoalLinkOption extends StatelessWidget {
  const _GoalLinkOption({
    required this.label,
    required this.subtitle,
    required this.icon,
    required this.onTap,
    this.selected = false,
  });

  final String label;
  final String subtitle;
  final IconData icon;
  final VoidCallback onTap;
  final bool selected;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Material(
        color: selected
            ? const Color(0xFFFFF6CF)
            : Colors.white.withValues(alpha: 0.7),
        borderRadius: BorderRadius.circular(22),
        child: InkWell(
          borderRadius: BorderRadius.circular(22),
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Row(
              children: [
                Container(
                  width: 40,
                  height: 40,
                  decoration: BoxDecoration(
                    color: const Color(0xFFF4F1EB),
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: Icon(icon, color: const Color(0xFFFFC815), size: 20),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        label,
                        style: const TextStyle(
                          fontSize: 14.5,
                          fontWeight: FontWeight.w800,
                          color: Color(0xFF1B1C1A),
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        subtitle,
                        style: const TextStyle(
                          fontSize: 12.5,
                          color: Color(0xFF4B444D),
                        ),
                      ),
                    ],
                  ),
                ),
                if (selected)
                  const Icon(Icons.check_rounded, color: Color(0xFFFFC815)),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _DetailCard extends StatelessWidget {
  const _DetailCard({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.72),
        borderRadius: BorderRadius.circular(28),
        border: Border.all(color: Colors.white.withValues(alpha: 0.9)),
      ),
      child: child,
    );
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle({required this.title, required this.count});

  final String title;
  final int count;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Text(
          title,
          style: const TextStyle(
            fontFamily: 'Manrope',
            fontSize: 22,
            fontWeight: FontWeight.w800,
            color: Color(0xFF1B1C1A),
          ),
        ),
        const Spacer(),
        Text(
          '$count',
          style: const TextStyle(
            fontWeight: FontWeight.w700,
            color: Color(0xFF4B444D),
          ),
        ),
      ],
    );
  }
}

class _LinkedTaskCard extends StatelessWidget {
  const _LinkedTaskCard({required this.task, required this.onTap});

  final Map<String, dynamic> task;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.white.withValues(alpha: 0.68),
      borderRadius: BorderRadius.circular(22),
      child: InkWell(
        borderRadius: BorderRadius.circular(22),
        onTap: onTap,
        child: Container(
          margin: const EdgeInsets.only(bottom: 10),
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(22),
            border: Border.all(color: const Color(0xFFE6E1D6)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                task['title']?.toString() ?? 'Untitled task',
                style: const TextStyle(
                  fontSize: 14.5,
                  fontWeight: FontWeight.w800,
                  color: Color(0xFF1B1C1A),
                ),
              ),
              const SizedBox(height: 4),
              Text(
                task['notes']?.toString().isNotEmpty == true
                    ? task['notes'].toString()
                    : 'No notes',
                style: const TextStyle(
                  fontSize: 12.5,
                  height: 1.45,
                  color: Color(0xFF4B444D),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _LinkedReflectionCard extends StatelessWidget {
  const _LinkedReflectionCard({required this.reflection, required this.onTap});

  final Map<String, dynamic> reflection;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Material(
        color: Colors.white.withValues(alpha: 0.68),
        borderRadius: BorderRadius.circular(22),
        child: InkWell(
          borderRadius: BorderRadius.circular(22),
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Row(
              children: [
                Container(
                  width: 40,
                  height: 40,
                  decoration: BoxDecoration(
                    color: const Color(0xFFF4F1EB),
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: const Icon(
                    Icons.auto_stories_rounded,
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
                        reflection['type']?.toString().toUpperCase() ??
                            'REFLECTION',
                        style: const TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w800,
                          color: Color(0xFF1B1C1A),
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        reflection['mood']?.toString() ?? 'neutral',
                        style: const TextStyle(
                          fontSize: 12.5,
                          color: Color(0xFF4B444D),
                        ),
                      ),
                    ],
                  ),
                ),
                const Icon(
                  Icons.arrow_forward_rounded,
                  size: 18,
                  color: Color(0xFF1B1C1A),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _EmptyCard extends StatelessWidget {
  const _EmptyCard({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.65),
        borderRadius: BorderRadius.circular(22),
      ),
      child: Text(
        text,
        style: const TextStyle(
          fontSize: 13.5,
          height: 1.5,
          color: Color(0xFF4B444D),
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

class _Block extends StatelessWidget {
  const _Block({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: const TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w800,
              color: Color(0xFFFFC815),
            ),
          ),
          const SizedBox(height: 3),
          Text(
            value,
            style: const TextStyle(
              fontSize: 13.5,
              height: 1.5,
              color: Color(0xFF4B444D),
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
