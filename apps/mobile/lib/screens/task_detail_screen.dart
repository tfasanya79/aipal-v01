import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/app_state.dart';
import 'goal_reflection_detail_screens.dart';

class TaskDetailScreen extends StatefulWidget {
  const TaskDetailScreen({super.key, required this.taskId});

  final String taskId;

  @override
  State<TaskDetailScreen> createState() => _TaskDetailScreenState();
}

class _TaskDetailScreenState extends State<TaskDetailScreen> {
  Future<Map<String, dynamic>>? _detailFuture;

  @override
  void initState() {
    super.initState();
    _detailFuture = _load();
  }

  Future<Map<String, dynamic>> _load() =>
      context.read<AppState>().api.getTaskDetail(widget.taskId);

  Future<void> _refresh() async {
    if (!mounted) return;
    setState(() {
      _detailFuture = _load();
    });
  }

  Future<void> _editTask(Map<String, dynamic> task) async {
    final appState = context.read<AppState>();
    final titleController = TextEditingController(
      text: task['title']?.toString() ?? '',
    );
    final notesController = TextEditingController(
      text: task['notes']?.toString() ?? '',
    );
    final dueController = TextEditingController(
      text: task['due_at']?.toString().split('T').first ?? '',
    );

    final result = await showModalBottomSheet<Map<String, dynamic>>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _TaskEditorSheet(
        titleController: titleController,
        notesController: notesController,
        dueController: dueController,
      ),
    );

    titleController.dispose();
    notesController.dispose();
    dueController.dispose();

    if (result == null) return;
    await appState.updateTask(
      task['id'] as int,
      title: result['title']?.toString(),
      notes: result['notes']?.toString(),
      dueAt: result['due_at'] as DateTime?,
    );
    if (!mounted) return;
    await _refresh();
  }

  Future<void> _toggleComplete(Map<String, dynamic> task) async {
    final appState = context.read<AppState>();
    final status = task['status']?.toString() ?? 'planned';
    await appState.updateTask(
      task['id'] as int,
      status: status == 'done' ? 'planned' : 'done',
    );
    if (!mounted) return;
    await _refresh();
  }

  Future<void> _deleteTask(Map<String, dynamic> task) async {
    final appState = context.read<AppState>();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete task?'),
        content: const Text('This removes the task permanently.'),
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
    await appState.deleteTask(task['id'] as int);
    if (mounted) Navigator.pop(context);
  }

  Future<void> _linkGoal(Map<String, dynamic>? task) async {
    final appState = context.read<AppState>();
    final api = appState.api;
    final goals = await api.listGoals();
    if (!mounted) return;

    final selected = await showModalBottomSheet<String?>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _GoalPickerSheet(
        goals: goals.cast<Map<String, dynamic>>(),
        currentGoalId: task?['goal_id']?.toString(),
      ),
    );

    if (selected == null) return;
    await appState.updateTask(
      task!['id'] as int,
      goalId: selected.isEmpty ? null : selected,
    );
    if (!mounted) return;
    await _refresh();
  }

  void _openGoal(Map<String, dynamic> goal) {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => GoalDetailScreen(goalId: goal['id'].toString()),
      ),
    );
  }

  String _formatDate(String? raw) {
    if (raw == null || raw.isEmpty) return 'Flexible';
    try {
      final dt = DateTime.parse(raw).toLocal();
      final hour = dt.hour % 12 == 0 ? 12 : dt.hour % 12;
      final minute = dt.minute.toString().padLeft(2, '0');
      final period = dt.hour >= 12 ? 'PM' : 'AM';
      return '${dt.year}-${dt.month.toString().padLeft(2, '0')}-${dt.day.toString().padLeft(2, '0')} · $hour:$minute $period';
    } catch (_) {
      return raw;
    }
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
            final task = (data?['task'] as Map?)?.cast<String, dynamic>();
            final goal = (data?['linked_goal'] as Map?)
                ?.cast<String, dynamic>();
            final subtasks =
                (data?['subtasks'] as List?)?.cast<Map<String, dynamic>>() ??
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
                              task?['title']?.toString() ?? 'Task detail',
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                fontFamily: 'Manrope',
                                fontSize: 28,
                                fontWeight: FontWeight.w800,
                                color: Color(0xFF1B1C1A),
                              ),
                            ),
                            const SizedBox(height: 2),
                            const Text(
                              'Edit, link, and keep the work organized',
                              style: TextStyle(
                                fontSize: 13,
                                color: Color(0xFF575C6B),
                              ),
                            ),
                          ],
                        ),
                      ),
                      IconButton(
                        onPressed: _refresh,
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
                            task == null)
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
                                          task?['status']?.toString() ??
                                          'planned',
                                    ),
                                    _Chip(
                                      label:
                                          task?['priority']?.toString() ??
                                          'medium',
                                    ),
                                    if ((task?['due_at']?.toString() ?? '')
                                        .isNotEmpty)
                                      _Chip(
                                        label: _formatDate(
                                          task?['due_at']?.toString(),
                                        ),
                                      ),
                                    if ((goal?['title']?.toString() ?? '')
                                        .isNotEmpty)
                                      _Chip(label: goal!['title'].toString()),
                                  ],
                                ),
                                const SizedBox(height: 14),
                                Text(
                                  task?['notes']?.toString().isNotEmpty == true
                                      ? task!['notes'].toString()
                                      : 'No notes added yet.',
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
                                      onPressed: task == null
                                          ? null
                                          : () => _toggleComplete(task),
                                      icon: const Icon(
                                        Icons.done_rounded,
                                        size: 18,
                                      ),
                                      label: Text(
                                        (task?['status']?.toString() ??
                                                    'planned') ==
                                                'done'
                                            ? 'Mark open'
                                            : 'Mark done',
                                      ),
                                    ),
                                    OutlinedButton.icon(
                                      onPressed: task == null
                                          ? null
                                          : () => _editTask(task),
                                      icon: const Icon(
                                        Icons.edit_rounded,
                                        size: 18,
                                      ),
                                      label: const Text('Edit'),
                                    ),
                                    OutlinedButton.icon(
                                      onPressed: task == null
                                          ? null
                                          : () => _linkGoal(task),
                                      icon: Icon(
                                        goal == null
                                            ? Icons.flag_rounded
                                            : Icons.flag_outlined,
                                        size: 18,
                                      ),
                                      label: Text(
                                        goal == null
                                            ? 'Link goal'
                                            : 'Change goal',
                                      ),
                                    ),
                                    FilledButton.tonalIcon(
                                      onPressed: task == null
                                          ? null
                                          : () => _deleteTask(task),
                                      icon: const Icon(
                                        Icons.delete_rounded,
                                        size: 18,
                                      ),
                                      label: const Text('Delete'),
                                    ),
                                  ],
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(height: 18),
                          _SectionTitle(
                            title: 'Linked goal',
                            count: goal == null ? 0 : 1,
                          ),
                          const SizedBox(height: 12),
                          if (goal == null)
                            const _EmptyCard(text: 'No goal is linked yet.')
                          else
                            _GoalPreviewCard(
                              goal: goal,
                              onTap: () => _openGoal(goal),
                              onClear: task == null
                                  ? null
                                  : () => _linkGoal(task),
                            ),
                          const SizedBox(height: 18),
                          _SectionTitle(
                            title: 'Subtasks',
                            count: subtasks.length,
                          ),
                          const SizedBox(height: 12),
                          if (subtasks.isEmpty)
                            const _EmptyCard(text: 'No subtasks created yet.')
                          else
                            ...subtasks.map(
                              (subtask) => _SubtaskCard(task: subtask),
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

class _TaskEditorSheet extends StatelessWidget {
  const _TaskEditorSheet({
    required this.titleController,
    required this.notesController,
    required this.dueController,
  });

  final TextEditingController titleController;
  final TextEditingController notesController;
  final TextEditingController dueController;

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
          border: Border.all(color: Colors.white.withValues(alpha: 0.9)),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const _SheetHandle(),
            const SizedBox(height: 18),
            _Field(controller: titleController, label: 'Task title'),
            const SizedBox(height: 12),
            _Field(controller: notesController, label: 'Notes', maxLines: 4),
            const SizedBox(height: 12),
            _Field(controller: dueController, label: 'Due date (YYYY-MM-DD)'),
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                onPressed: () {
                  Navigator.pop(context, {
                    'title': titleController.text.trim(),
                    'notes': notesController.text.trim(),
                    'due_at': _parseDate(dueController.text.trim()),
                  });
                },
                child: const Text('Save Task'),
              ),
            ),
          ],
        ),
      ),
    );
  }

  DateTime? _parseDate(String raw) {
    if (raw.isEmpty) return null;
    try {
      return DateTime.parse(raw);
    } catch (_) {
      return null;
    }
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
          border: Border.all(color: Colors.white.withValues(alpha: 0.9)),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const _SheetHandle(),
            const SizedBox(height: 18),
            const Align(
              alignment: Alignment.centerLeft,
              child: Text(
                'Link to goal',
                style: TextStyle(
                  fontFamily: 'Manrope',
                  fontSize: 22,
                  fontWeight: FontWeight.w800,
                  color: Color(0xFF1B1C1A),
                ),
              ),
            ),
            const SizedBox(height: 12),
            _GoalOption(
              label: 'No goal',
              subtitle: 'Keep this task standalone.',
              icon: Icons.link_off_rounded,
              selected: currentGoalId == null || currentGoalId!.isEmpty,
              onTap: () => Navigator.pop(context, ''),
            ),
            const SizedBox(height: 8),
            ...goals.map(
              (goal) => _GoalOption(
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

class _GoalOption extends StatelessWidget {
  const _GoalOption({
    required this.label,
    required this.subtitle,
    required this.icon,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final String subtitle;
  final IconData icon;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Material(
        color: selected
            ? const Color(0xFFFFF6CF)
            : Colors.white.withValues(alpha: 0.68),
        borderRadius: BorderRadius.circular(20),
        child: InkWell(
          borderRadius: BorderRadius.circular(20),
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
                  const Icon(
                    Icons.check_rounded,
                    color: Color(0xFFFFC815),
                    size: 18,
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _GoalPreviewCard extends StatelessWidget {
  const _GoalPreviewCard({
    required this.goal,
    required this.onTap,
    required this.onClear,
  });

  final Map<String, dynamic> goal;
  final VoidCallback onTap;
  final VoidCallback? onClear;

  @override
  Widget build(BuildContext context) {
    return Material(
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
                width: 42,
                height: 42,
                decoration: BoxDecoration(
                  color: const Color(0xFFF4F1EB),
                  borderRadius: BorderRadius.circular(14),
                ),
                child: const Icon(
                  Icons.flag_rounded,
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
                      goal['title']?.toString() ?? 'Linked goal',
                      style: const TextStyle(
                        fontSize: 14.5,
                        fontWeight: FontWeight.w800,
                        color: Color(0xFF1B1C1A),
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      goal['life_area']?.toString() ?? 'Goal',
                      style: const TextStyle(
                        fontSize: 12.5,
                        color: Color(0xFF4B444D),
                      ),
                    ),
                  ],
                ),
              ),
              if (onClear != null)
                TextButton(onPressed: onClear, child: const Text('Unlink')),
            ],
          ),
        ),
      ),
    );
  }
}

class _SubtaskCard extends StatelessWidget {
  const _SubtaskCard({required this.task});

  final Map<String, dynamic> task;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.68),
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

class _DetailCard extends StatelessWidget {
  const _DetailCard({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.7),
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

class _EmptyCard extends StatelessWidget {
  const _EmptyCard({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.62),
        borderRadius: BorderRadius.circular(22),
        border: Border.all(color: const Color(0xFFE6E1D6)),
      ),
      child: Text(
        text,
        style: const TextStyle(
          fontSize: 13.5,
          height: 1.45,
          color: Color(0xFF4B444D),
        ),
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
      decoration: InputDecoration(
        labelText: label,
        filled: true,
        fillColor: Colors.white.withValues(alpha: 0.75),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(maxLines > 1 ? 20 : 999),
        ),
      ),
    );
  }
}
