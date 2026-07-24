import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/app_state.dart';
import '../services/web_title.dart';
import '../widgets/plan_draft_card.dart';
import '../widgets/today/focus_timer_bar.dart';
import '../widgets/today/today_empty.dart';
import 'task_detail_screen.dart';

class TodayScreen extends StatefulWidget {
  const TodayScreen({super.key});

  @override
  State<TodayScreen> createState() => _TodayScreenState();
}

class _TodayScreenState extends State<TodayScreen> {
  bool _completedExpanded = false;
  String? _lastWebTitle;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<AppState>().refreshTodayView();
    });
  }

  Future<void> _suggestDay(AppState state, {String? template}) async {
    await state.suggestDayPlan(template: template);
    if (!mounted) return;

    final notice = state.suggestDayNotice;
    if (notice != null) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(notice)));
      state.clearSuggestDayNotice();
    }
  }

  Future<void> _addTask() async {
    final titleController = TextEditingController();
    final noteController = TextEditingController();

    final result = await showModalBottomSheet<Map<String, String>>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _PremiumTaskSheet(
        titleController: titleController,
        noteController: noteController,
      ),
    );

    titleController.dispose();
    noteController.dispose();

    final title = result?['title']?.trim() ?? '';
    final notes = result?['notes']?.trim();

    if (title.isNotEmpty && mounted) {
      await context.read<AppState>().createTask(
        title,
        notes: notes?.isNotEmpty == true ? notes : null,
      );
    }
  }

  void _openReview(AppState state) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _PremiumReviewSheet(
        openTasks: state.openTasksForReview,
        onDefer: () async {
          Navigator.pop(context);
          await state.deferOpenTasks();
        },
        onGoLive: () {
          Navigator.pop(context);
          state.goToTab(0);
          state.toggleLive();
        },
      ),
    );
  }

  Future<void> _showSuggestSheet(AppState state) async {
    final template = await showModalBottomSheet<String>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => const _SuggestPlanSheet(),
    );

    if (template != null && mounted) {
      await _suggestDay(state, template: template);
    }
  }

  void _openTaskDetail(Map<String, dynamic> task) {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => TaskDetailScreen(taskId: task['id'].toString()),
      ),
    );
  }

  Future<void> _loadAndReview(AppState state) async {
    await state.loadEveningPayload();
    if (mounted) _openReview(state);
  }

  void _syncWebTitle(String title) {
    if (!kIsWeb || _lastWebTitle == title) return;
    _lastWebTitle = title;
    setWebPageTitle(title);
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<AppState>(
      builder: (context, state, _) {
        _syncWebTitle('Today · AiPal');
        final view = state.todayView;
        final summary = view?['summary'] as Map<String, dynamic>?;
        final sections = view?['sections'] as Map<String, dynamic>?;
        final upNext = view?['up_next'] as Map<String, dynamic>?;
        final todayItems =
            (view?['today_items'] as List?)?.cast<Map<String, dynamic>>() ?? [];
        final agendaOpen = todayItems
            .where(
              (item) => !{
                'completed',
                'cancelled',
                'dismissed',
              }.contains(item['status']?.toString()),
            )
            .toList();
        final agendaCompleted = todayItems
            .where((item) => item['status']?.toString() == 'completed')
            .toList();

        final now =
            (sections?['now'] as List?)?.cast<Map<String, dynamic>>() ?? [];
        final upcoming =
            (sections?['upcoming'] as List?)?.cast<Map<String, dynamic>>() ??
            [];
        final completed =
            (sections?['completed'] as List?)?.cast<Map<String, dynamic>>() ??
            [];

        final focus = state.focusTask;
        final planDraft = state.pendingPlanDraft;

        final done = summary?['done'] as int? ?? 0;
        final total = summary?['total'] as int? ?? 0;
        final streak = summary?['streak_days'] as int? ?? 0;

        return Scaffold(
          backgroundColor: const Color(0xFFFAF9F5),
          floatingActionButton: FloatingActionButton(
            backgroundColor: const Color(0xFFFFC815),
            foregroundColor: Colors.white,
            onPressed: _addTask,
            child: const Icon(Icons.add_rounded),
          ),
          body: Stack(
            children: [
              const _TodayBackground(),
              Column(
                children: [
                  if (focus != null)
                    FocusTimerBar(
                      taskTitle: focus['title'] as String,
                      totalSeconds: state.focusSeconds,
                      onComplete: () => state.completeFocusTask(),
                      onCancel: () => state.cancelFocus(),
                    ),
                  Expanded(
                    child: RefreshIndicator(
                      onRefresh: state.refreshTodayView,
                      child: view == null
                          ? const Center(child: CircularProgressIndicator())
                          : ListView(
                              padding: const EdgeInsets.fromLTRB(
                                20,
                                34,
                                20,
                                96,
                              ),
                              children: [
                                _TodayHeader(
                                  done: done,
                                  total: total,
                                  streak: streak,
                                  onReview: () => _loadAndReview(state),
                                ),
                                const SizedBox(height: 22),

                                _RoutineChips(
                                  busy: state.loading,
                                  onSelect: (template) =>
                                      _suggestDay(state, template: template),
                                  onSuggest: () => _showSuggestSheet(state),
                                ),

                                const SizedBox(height: 18),

                                if (planDraft != null)
                                  _GlassPanel(
                                    child: PlanDraftCard(
                                      draft: planDraft,
                                      onConfirm: state.confirmPlanDraft,
                                      onDiscard: state.discardPlanDraft,
                                    ),
                                  ),

                                if ((summary?['total'] as int? ?? 0) == 0 &&
                                    upNext == null &&
                                    todayItems.isEmpty) ...[
                                  const SizedBox(height: 20),
                                  SizedBox(
                                    height:
                                        MediaQuery.of(context).size.height *
                                        0.35,
                                    child: TodayEmpty(
                                      onGoCompanion: () => state.goToTab(0),
                                    ),
                                  ),
                                ] else ...[
                                  const SizedBox(height: 20),
                                  LayoutBuilder(
                                    builder: (context, constraints) {
                                      final desktop =
                                          constraints.maxWidth >= 920;

                                      if (!desktop) {
                                        return Column(
                                          children: [
                                            if (agendaOpen.isNotEmpty)
                                              _AgendaColumn(
                                                open: agendaOpen,
                                                completed: agendaCompleted,
                                                completedExpanded:
                                                    _completedExpanded,
                                                onToggleCompleted: () =>
                                                    setState(
                                                      () => _completedExpanded =
                                                          !_completedExpanded,
                                                    ),
                                                onComplete:
                                                    state.completeTodayItem,
                                                onSnooze: (id) =>
                                                    state.snoozeTodayItem(id),
                                                onStartFocus: (item) => state
                                                    .startFocusTodayItem(item),
                                                onCancel: state.cancelTodayItem,
                                              )
                                            else if (upNext != null)
                                              _UpNextPremiumCard(
                                                task: upNext,
                                                onStartFocus: () =>
                                                    state.startFocus(upNext),
                                                onOpen: () =>
                                                    _openTaskDetail(upNext),
                                                onDone: () =>
                                                    state.completeTask(
                                                      upNext['id'] as int,
                                                    ),
                                                onBreakdown: () =>
                                                    state.breakdownTask(
                                                      upNext['id'] as int,
                                                    ),
                                              ),
                                            const SizedBox(height: 22),
                                            if (agendaOpen.isEmpty)
                                              _TasksColumn(
                                                now: now,
                                                upcoming: upcoming,
                                                completed: completed,
                                                completedExpanded:
                                                    _completedExpanded,
                                                onToggleCompleted: () =>
                                                    setState(
                                                      () => _completedExpanded =
                                                          !_completedExpanded,
                                                    ),
                                                onOpenTask: _openTaskDetail,
                                                onComplete: (id) =>
                                                    state.completeTask(id),
                                              ),
                                            const SizedBox(height: 22),
                                            _FocusLanesPanel(
                                              tasks: [...now, ...upcoming],
                                            ),
                                          ],
                                        );
                                      }

                                      return Row(
                                        crossAxisAlignment:
                                            CrossAxisAlignment.start,
                                        children: [
                                          Expanded(
                                            flex: 2,
                                            child: Column(
                                              children: [
                                                if (agendaOpen.isNotEmpty)
                                                  _AgendaColumn(
                                                    open: agendaOpen,
                                                    completed: agendaCompleted,
                                                    completedExpanded:
                                                        _completedExpanded,
                                                    onToggleCompleted: () => setState(
                                                      () => _completedExpanded =
                                                          !_completedExpanded,
                                                    ),
                                                    onComplete:
                                                        state.completeTodayItem,
                                                    onSnooze: (id) => state
                                                        .snoozeTodayItem(id),
                                                    onStartFocus: (item) => state
                                                        .startFocusTodayItem(
                                                          item,
                                                        ),
                                                    onCancel:
                                                        state.cancelTodayItem,
                                                  )
                                                else if (upNext != null)
                                                  _UpNextPremiumCard(
                                                    task: upNext,
                                                    onStartFocus: () => state
                                                        .startFocus(upNext),
                                                    onOpen: () =>
                                                        _openTaskDetail(upNext),
                                                    onDone: () =>
                                                        state.completeTask(
                                                          upNext['id'] as int,
                                                        ),
                                                    onBreakdown: () =>
                                                        state.breakdownTask(
                                                          upNext['id'] as int,
                                                        ),
                                                  ),
                                                const SizedBox(height: 22),
                                                if (agendaOpen.isEmpty)
                                                  _TasksColumn(
                                                    now: now,
                                                    upcoming: upcoming,
                                                    completed: completed,
                                                    completedExpanded:
                                                        _completedExpanded,
                                                    onToggleCompleted: () => setState(
                                                      () => _completedExpanded =
                                                          !_completedExpanded,
                                                    ),
                                                    onOpenTask: _openTaskDetail,
                                                    onComplete: (id) =>
                                                        state.completeTask(id),
                                                  ),
                                              ],
                                            ),
                                          ),
                                          const SizedBox(width: 24),
                                          SizedBox(
                                            width: 330,
                                            child: _FocusLanesPanel(
                                              tasks: [...now, ...upcoming],
                                            ),
                                          ),
                                        ],
                                      );
                                    },
                                  ),
                                ],
                              ],
                            ),
                    ),
                  ),
                ],
              ),
            ],
          ),
        );
      },
    );
  }
}

class _TodayHeader extends StatelessWidget {
  const _TodayHeader({
    required this.done,
    required this.total,
    required this.streak,
    required this.onReview,
  });

  final int done;
  final int total;
  final int streak;
  final VoidCallback onReview;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final compact = constraints.maxWidth < 560;
        final heading = Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'My Day',
              style: TextStyle(
                fontFamily: 'Manrope',
                fontSize: 44,
                height: 1,
                fontWeight: FontWeight.w800,
                letterSpacing: -1.4,
                color: Color(0xFF1B1C1A),
              ),
            ),
            const SizedBox(height: 14),
            Wrap(
              spacing: 16,
              runSpacing: 8,
              children: [
                _MiniStat(
                  value: '$done/$total',
                  label: 'items completed',
                  icon: Icons.check_circle_outline_rounded,
                ),
                _MiniStat(
                  value: '$streak day',
                  label: 'streak',
                  icon: Icons.trending_up_rounded,
                ),
              ],
            ),
          ],
        );

        if (compact) {
          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              heading,
              const SizedBox(height: 16),
              Align(
                alignment: Alignment.centerLeft,
                child: _GlassButton(
                  icon: Icons.history_edu_rounded,
                  label: 'Review Progress',
                  onTap: onReview,
                ),
              ),
            ],
          );
        }

        return Row(
          children: [
            Expanded(child: heading),
            _GlassButton(
              icon: Icons.history_edu_rounded,
              label: 'Review Progress',
              onTap: onReview,
            ),
          ],
        );
      },
    );
  }
}

class _RoutineChips extends StatelessWidget {
  const _RoutineChips({
    required this.busy,
    required this.onSelect,
    required this.onSuggest,
  });

  final bool busy;
  final ValueChanged<String> onSelect;
  final VoidCallback onSuggest;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 10,
      runSpacing: 10,
      children: [
        _ChipButton(label: 'Work', onTap: () => onSelect('work')),
        _ChipButton(label: 'Deep Work', onTap: () => onSelect('deep_work')),
        _ChipButton(label: 'Wellness', onTap: () => onSelect('wellness')),
        _GradientChip(busy: busy, label: 'Suggest for me', onTap: onSuggest),
      ],
    );
  }
}

class _UpNextPremiumCard extends StatelessWidget {
  const _UpNextPremiumCard({
    required this.task,
    required this.onStartFocus,
    required this.onOpen,
    required this.onDone,
    required this.onBreakdown,
  });

  final Map<String, dynamic> task;
  final VoidCallback onStartFocus;
  final VoidCallback onOpen;
  final VoidCallback onDone;
  final VoidCallback onBreakdown;

  @override
  Widget build(BuildContext context) {
    final title = task['title']?.toString() ?? 'Untitled task';
    final duration =
        task['estimated_minutes']?.toString() ??
        task['duration_minutes']?.toString() ??
        '25';
    final priority = task['priority']?.toString().toLowerCase() ?? 'medium';
    final isHigh = priority == 'high' || priority == 'critical';

    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onOpen,
        borderRadius: BorderRadius.circular(34),
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.all(1.4),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(34),
            gradient: LinearGradient(
              colors: [
                const Color(0xFFFFC815).withValues(alpha: 0.28),
                const Color(0xFF003B2B).withValues(alpha: 0.16),
              ],
            ),
          ),
          child: Container(
            padding: const EdgeInsets.all(24),
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.68),
              borderRadius: BorderRadius.circular(33),
              border: Border.all(color: Colors.white.withValues(alpha: 0.9)),
              boxShadow: [
                BoxShadow(
                  color: const Color(0xFF1A1F2C).withValues(alpha: 0.05),
                  blurRadius: 40,
                  offset: const Offset(0, 22),
                ),
              ],
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 12,
                        vertical: 7,
                      ),
                      decoration: BoxDecoration(
                        color: const Color(0xFFFFF2B8).withValues(alpha: 0.72),
                        borderRadius: BorderRadius.circular(999),
                      ),
                      child: const Text(
                        'UP NEXT',
                        style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w900,
                          letterSpacing: 1.4,
                          color: Color(0xFFFFC815),
                        ),
                      ),
                    ),
                    const Spacer(),
                    _PriorityPill(
                      label: priority,
                      color: isHigh
                          ? const Color(0xFFBA1A1A)
                          : const Color(0xFF003B2B),
                      background: isHigh
                          ? const Color(0xFFFFDAD6)
                          : const Color(0xFFB4E9E9),
                    ),
                  ],
                ),
                const SizedBox(height: 20),
                Text(
                  title,
                  softWrap: true,
                  style: const TextStyle(
                    fontFamily: 'Manrope',
                    fontSize: 26,
                    height: 1.22,
                    fontWeight: FontWeight.w900,
                    letterSpacing: -0.4,
                    color: Color(0xFF1B1C1A),
                  ),
                ),
                const SizedBox(height: 16),
                Row(
                  children: [
                    _SoftMetaChip(
                      icon: Icons.schedule_rounded,
                      label: '$duration mins',
                    ),
                    const SizedBox(width: 10),
                    const _SoftMetaChip(
                      icon: Icons.bolt_rounded,
                      label: 'Focus block',
                    ),
                  ],
                ),
                const SizedBox(height: 24),
                Row(
                  children: [
                    Expanded(
                      child: _PrimaryActionButton(
                        icon: Icons.play_arrow_rounded,
                        label: 'Start Focus',
                        onTap: onStartFocus,
                      ),
                    ),
                    const SizedBox(width: 10),
                    _RoundActionButton(
                      icon: Icons.done_rounded,
                      tooltip: 'Mark done',
                      onTap: onDone,
                    ),
                    const SizedBox(width: 10),
                    _RoundActionButton(
                      icon: Icons.account_tree_rounded,
                      tooltip: 'Break down',
                      onTap: onBreakdown,
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

class _SoftMetaChip extends StatelessWidget {
  const _SoftMetaChip({required this.icon, required this.label});

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
      decoration: BoxDecoration(
        color: const Color(0xFFF4F4F0),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: const Color(0xFFE3E2DF)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 17, color: const Color(0xFFFFC815)),
          const SizedBox(width: 6),
          Text(
            label,
            style: const TextStyle(
              fontSize: 12.5,
              fontWeight: FontWeight.w800,
              color: Color(0xFF4B444D),
            ),
          ),
        ],
      ),
    );
  }
}

class _RoundActionButton extends StatelessWidget {
  const _RoundActionButton({
    required this.icon,
    required this.tooltip,
    required this.onTap,
  });

  final IconData icon;
  final String tooltip;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: tooltip,
      child: Material(
        color: Colors.white.withValues(alpha: 0.7),
        shape: const CircleBorder(),
        child: InkWell(
          customBorder: const CircleBorder(),
          onTap: onTap,
          child: Container(
            width: 48,
            height: 48,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              border: Border.all(color: const Color(0xFFE3E2DF)),
            ),
            child: Icon(icon, size: 21, color: const Color(0xFFFFC815)),
          ),
        ),
      ),
    );
  }
}

class _AgendaColumn extends StatelessWidget {
  const _AgendaColumn({
    required this.open,
    required this.completed,
    required this.completedExpanded,
    required this.onToggleCompleted,
    required this.onComplete,
    required this.onSnooze,
    required this.onStartFocus,
    required this.onCancel,
  });

  final List<Map<String, dynamic>> open;
  final List<Map<String, dynamic>> completed;
  final bool completedExpanded;
  final VoidCallback onToggleCompleted;
  final ValueChanged<String> onComplete;
  final ValueChanged<String> onSnooze;
  final ValueChanged<Map<String, dynamic>> onStartFocus;
  final ValueChanged<String> onCancel;

  String _sectionFor(Map<String, dynamic> item) {
    if (item['status']?.toString() == 'completed') return 'Completed';
    final type = item['type']?.toString();
    if (type == 'meeting' || type == 'calendar') return 'Meetings';
    if (type == 'focus') return 'Focus';
    final raw = item['start_time']?.toString() ?? item['due_at']?.toString();
    final dt = raw == null ? null : DateTime.tryParse(raw)?.toLocal();
    if (dt == null) return 'Unscheduled';
    if (dt.hour < 12) return 'Morning';
    if (dt.hour >= 17) return 'Evening';
    return 'Work';
  }

  Map<String, List<Map<String, dynamic>>> _groupOpen() {
    final grouped = <String, List<Map<String, dynamic>>>{
      'Morning': [],
      'Work': [],
      'Meetings': [],
      'Focus': [],
      'Evening': [],
      'Unscheduled': [],
    };
    for (final item in open) {
      grouped[_sectionFor(item)]?.add(item);
    }
    grouped.removeWhere((_, items) => items.isEmpty);
    return grouped;
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _SectionHeader(title: 'Personal Agenda', count: open.length),
        const SizedBox(height: 14),
        if (open.isEmpty)
          const _EmptyGlassMessage()
        else
          ..._groupOpen().entries.expand(
            (entry) => [
              _AgendaTimelineHeader(
                title: entry.key,
                count: entry.value.length,
              ),
              const SizedBox(height: 10),
              ...entry.value.map(
                (item) => _AgendaItemTile(
                  item: item,
                  onComplete: () => onComplete(item['id'].toString()),
                  onSnooze: () => onSnooze(item['id'].toString()),
                  onStartFocus: () => onStartFocus(item),
                  onCancel: () => onCancel(item['id'].toString()),
                ),
              ),
              const SizedBox(height: 8),
            ],
          ),
        if (completed.isNotEmpty) ...[
          const SizedBox(height: 24),
          InkWell(
            onTap: onToggleCompleted,
            borderRadius: BorderRadius.circular(20),
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 8),
              child: Row(
                children: [
                  const Expanded(
                    child: Text(
                      'Completed',
                      style: TextStyle(
                        fontFamily: 'Manrope',
                        fontSize: 22,
                        fontWeight: FontWeight.w800,
                        color: Color(0xFF1B1C1A),
                      ),
                    ),
                  ),
                  Text(
                    '${completed.length}',
                    style: const TextStyle(
                      color: Color(0xFF1B1C1A),
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Icon(
                    completedExpanded
                        ? Icons.expand_less_rounded
                        : Icons.expand_more_rounded,
                    color: const Color(0xFF1B1C1A),
                  ),
                ],
              ),
            ),
          ),
          if (completedExpanded)
            ...completed.map(
              (item) => _AgendaItemTile(
                item: item,
                completed: true,
                onComplete: () {},
                onSnooze: () {},
                onStartFocus: () {},
                onCancel: () {},
              ),
            ),
        ],
      ],
    );
  }
}

class _AgendaItemTile extends StatelessWidget {
  const _AgendaItemTile({
    required this.item,
    required this.onComplete,
    required this.onSnooze,
    required this.onStartFocus,
    required this.onCancel,
    this.completed = false,
  });

  final Map<String, dynamic> item;
  final VoidCallback onComplete;
  final VoidCallback onSnooze;
  final VoidCallback onStartFocus;
  final VoidCallback onCancel;
  final bool completed;

  String _timeLabel() {
    final raw = item['start_time']?.toString() ?? item['due_at']?.toString();
    if (raw == null || raw.isEmpty) return 'Flexible';
    try {
      final dt = DateTime.parse(raw).toLocal();
      final hour = dt.hour % 12 == 0 ? 12 : dt.hour % 12;
      final minute = dt.minute.toString().padLeft(2, '0');
      final period = dt.hour >= 12 ? 'PM' : 'AM';
      return '$hour:$minute $period';
    } catch (_) {
      return raw;
    }
  }

  String _typeLabel() {
    final raw = item['type']?.toString() ?? 'task';
    return raw
        .split('_')
        .map(
          (part) => part.isEmpty
              ? part
              : '${part[0].toUpperCase()}${part.substring(1)}',
        )
        .join(' ');
  }

  IconData _icon() {
    switch (item['type']?.toString()) {
      case 'reminder':
        return Icons.notifications_active_rounded;
      case 'meeting':
      case 'calendar':
        return Icons.groups_rounded;
      case 'commitment':
        return Icons.handshake_rounded;
      case 'habit':
        return Icons.repeat_rounded;
      case 'reflection':
        return Icons.auto_stories_rounded;
      case 'focus':
        return Icons.center_focus_strong_rounded;
      default:
        return Icons.check_circle_outline_rounded;
    }
  }

  @override
  Widget build(BuildContext context) {
    final title = item['title']?.toString() ?? 'Untitled';
    final source = item['source']?.toString() ?? 'conversation';
    final priority = item['priority']?.toString();
    final tile = Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: completed ? 0.34 : 0.62),
        borderRadius: BorderRadius.circular(26),
        border: Border.all(color: Colors.white.withValues(alpha: 0.88)),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF1A1F2C).withValues(alpha: 0.03),
            blurRadius: 22,
            offset: const Offset(0, 12),
          ),
        ],
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 46,
            height: 46,
            decoration: BoxDecoration(
              color: const Color(0xFF003B2B).withValues(alpha: 0.12),
              borderRadius: BorderRadius.circular(16),
            ),
            child: Icon(_icon(), color: const Color(0xFF003B2B), size: 22),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    _SoftMetaChip(
                      icon: Icons.schedule_rounded,
                      label: _timeLabel(),
                    ),
                    _SoftMetaChip(
                      icon: Icons.category_rounded,
                      label: _typeLabel(),
                    ),
                    if (priority != null)
                      _SoftMetaChip(icon: Icons.flag_rounded, label: priority),
                  ],
                ),
                const SizedBox(height: 12),
                Text(
                  title,
                  style: TextStyle(
                    fontFamily: 'Manrope',
                    fontSize: 17,
                    height: 1.3,
                    fontWeight: FontWeight.w800,
                    decoration: completed ? TextDecoration.lineThrough : null,
                    color: const Color(0xFF1B1C1A),
                  ),
                ),
                const SizedBox(height: 5),
                Text(
                  'Source: $source',
                  style: const TextStyle(
                    fontSize: 12.5,
                    color: Color(0xFF4B444D),
                  ),
                ),
              ],
            ),
          ),
          if (!completed) ...[
            const SizedBox(width: 10),
            _AgendaMoreActions(
              onComplete: onComplete,
              onSnooze: onSnooze,
              onStartFocus: onStartFocus,
              onCancel: onCancel,
            ),
          ],
        ],
      ),
    );

    if (completed) return tile;

    return Dismissible(
      key: ValueKey('today-item-${item['id']}-${item['status']}'),
      confirmDismiss: (direction) async {
        if (direction == DismissDirection.startToEnd) {
          onComplete();
        } else if (direction == DismissDirection.endToStart) {
          onSnooze();
        }
        return false;
      },
      background: const _SwipeActionBackground(
        icon: Icons.done_rounded,
        label: 'Complete',
        alignment: Alignment.centerLeft,
      ),
      secondaryBackground: const _SwipeActionBackground(
        icon: Icons.snooze_rounded,
        label: 'Snooze',
        alignment: Alignment.centerRight,
      ),
      child: tile,
    );
  }
}

class _AgendaMoreActions extends StatelessWidget {
  const _AgendaMoreActions({
    required this.onComplete,
    required this.onSnooze,
    required this.onStartFocus,
    required this.onCancel,
  });

  final VoidCallback onComplete;
  final VoidCallback onSnooze;
  final VoidCallback onStartFocus;
  final VoidCallback onCancel;

  @override
  Widget build(BuildContext context) {
    return PopupMenuButton<String>(
      tooltip: 'More agenda actions',
      color: const Color(0xFFFAF9F5),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
      icon: const Icon(Icons.more_horiz_rounded, color: Color(0xFFFFC815)),
      onSelected: (value) {
        switch (value) {
          case 'complete':
            onComplete();
          case 'snooze':
            onSnooze();
          case 'focus':
            onStartFocus();
          case 'cancel':
            onCancel();
        }
      },
      itemBuilder: (context) => const [
        PopupMenuItem(value: 'complete', child: Text('Complete')),
        PopupMenuItem(value: 'snooze', child: Text('Snooze')),
        PopupMenuItem(value: 'focus', child: Text('Start focus')),
        PopupMenuItem(value: 'cancel', child: Text('Cancel')),
      ],
    );
  }
}

class _SwipeActionBackground extends StatelessWidget {
  const _SwipeActionBackground({
    required this.icon,
    required this.label,
    required this.alignment,
  });

  final IconData icon;
  final String label;
  final Alignment alignment;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.symmetric(horizontal: 22),
      alignment: alignment,
      decoration: BoxDecoration(
        color: const Color(0xFF003B2B).withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(26),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, color: const Color(0xFF003B2B)),
          const SizedBox(width: 8),
          Text(
            label,
            style: const TextStyle(
              color: Color(0xFF003B2B),
              fontWeight: FontWeight.w900,
            ),
          ),
        ],
      ),
    );
  }
}

class _AgendaTimelineHeader extends StatelessWidget {
  const _AgendaTimelineHeader({required this.title, required this.count});

  final String title;
  final int count;

  IconData _icon() {
    switch (title) {
      case 'Morning':
        return Icons.wb_twilight_rounded;
      case 'Work':
        return Icons.business_center_rounded;
      case 'Meetings':
        return Icons.groups_rounded;
      case 'Focus':
        return Icons.center_focus_strong_rounded;
      case 'Evening':
        return Icons.nights_stay_rounded;
      default:
        return Icons.view_agenda_rounded;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Container(
          width: 34,
          height: 34,
          decoration: BoxDecoration(
            color: const Color(0xFFFFC815).withValues(alpha: 0.11),
            borderRadius: BorderRadius.circular(14),
          ),
          child: Icon(_icon(), size: 18, color: const Color(0xFFFFC815)),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: Text(
            title,
            style: const TextStyle(
              fontFamily: 'Manrope',
              fontSize: 18,
              fontWeight: FontWeight.w900,
              color: Color(0xFF1B1C1A),
            ),
          ),
        ),
        Text(
          '$count',
          style: const TextStyle(
            fontSize: 12,
            fontWeight: FontWeight.w900,
            color: Color(0xFF003B2B),
          ),
        ),
      ],
    );
  }
}

class _TasksColumn extends StatelessWidget {
  const _TasksColumn({
    required this.now,
    required this.upcoming,
    required this.completed,
    required this.completedExpanded,
    required this.onToggleCompleted,
    required this.onOpenTask,
    required this.onComplete,
  });

  final List<Map<String, dynamic>> now;
  final List<Map<String, dynamic>> upcoming;
  final List<Map<String, dynamic>> completed;
  final bool completedExpanded;
  final VoidCallback onToggleCompleted;
  final ValueChanged<Map<String, dynamic>> onOpenTask;
  final ValueChanged<int> onComplete;

  @override
  Widget build(BuildContext context) {
    final tasks = [...now, ...upcoming];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _SectionHeader(title: 'Upcoming', count: tasks.length),
        const SizedBox(height: 14),
        if (tasks.isEmpty)
          const _EmptyGlassMessage()
        else
          ...tasks.map(
            (task) => _PremiumTaskTile(
              task: task,
              onOpen: () => onOpenTask(task),
              onComplete: () => onComplete(task['id'] as int),
            ),
          ),
        if (completed.isNotEmpty) ...[
          const SizedBox(height: 24),
          InkWell(
            onTap: onToggleCompleted,
            borderRadius: BorderRadius.circular(20),
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 8),
              child: Row(
                children: [
                  const Expanded(
                    child: Text(
                      'Completed',
                      style: TextStyle(
                        fontFamily: 'Manrope',
                        fontSize: 22,
                        fontWeight: FontWeight.w800,
                        color: Color(0xFF1B1C1A),
                      ),
                    ),
                  ),
                  Text(
                    '${completed.length}',
                    style: const TextStyle(
                      color: Color(0xFF1B1C1A),
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Icon(
                    completedExpanded
                        ? Icons.expand_less_rounded
                        : Icons.expand_more_rounded,
                    color: const Color(0xFF1B1C1A),
                  ),
                ],
              ),
            ),
          ),
          if (completedExpanded)
            ...completed.map(
              (task) => _PremiumTaskTile(
                task: task,
                completed: true,
                onOpen: () => onOpenTask(task),
                onComplete: () {},
              ),
            ),
        ],
      ],
    );
  }
}

class _PremiumTaskTile extends StatelessWidget {
  const _PremiumTaskTile({
    required this.task,
    required this.onComplete,
    required this.onOpen,
    this.completed = false,
  });

  final Map<String, dynamic> task;
  final VoidCallback onComplete;
  final VoidCallback onOpen;
  final bool completed;

  @override
  Widget build(BuildContext context) {
    final title = task['title']?.toString() ?? 'Untitled task';
    final due =
        task['due_label']?.toString() ??
        task['scheduled_for']?.toString() ??
        'Flexible';
    final priority = task['priority']?.toString().toLowerCase() ?? 'medium';

    final isHigh = priority == 'high' || priority == 'critical';

    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onOpen,
        borderRadius: BorderRadius.circular(24),
        child: Container(
          margin: const EdgeInsets.only(bottom: 12),
          padding: const EdgeInsets.all(18),
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: completed ? 0.34 : 0.56),
            borderRadius: BorderRadius.circular(24),
            border: Border.all(color: Colors.white.withValues(alpha: 0.9)),
            boxShadow: [
              BoxShadow(
                color: const Color(0xFF1A1F2C).withValues(alpha: 0.025),
                blurRadius: 18,
                offset: const Offset(0, 10),
              ),
            ],
          ),
          child: Row(
            children: [
              InkWell(
                onTap: completed ? null : onComplete,
                borderRadius: BorderRadius.circular(999),
                child: Container(
                  width: 26,
                  height: 26,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: completed
                        ? const Color(0xFFFFC815)
                        : Colors.transparent,
                    border: Border.all(
                      color: completed
                          ? const Color(0xFFFFC815)
                          : const Color(0xFFFFC815).withValues(alpha: 0.28),
                      width: 2,
                    ),
                  ),
                  child: completed
                      ? const Icon(
                          Icons.check_rounded,
                          size: 16,
                          color: Colors.white,
                        )
                      : null,
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: TextStyle(
                        fontSize: 16.5,
                        height: 1.3,
                        fontWeight: FontWeight.w700,
                        decoration: completed
                            ? TextDecoration.lineThrough
                            : null,
                        color: completed
                            ? const Color(0xFF1B1C1A)
                            : const Color(0xFF1B1C1A),
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      due,
                      style: const TextStyle(
                        fontSize: 12.5,
                        color: Color(0xFF1B1C1A),
                      ),
                    ),
                  ],
                ),
              ),
              _PriorityPill(
                label: priority,
                color: isHigh
                    ? const Color(0xFFBA1A1A)
                    : const Color(0xFF003B2B),
                background: isHigh
                    ? const Color(0xFFFFDAD6)
                    : const Color(0xFFB4E9E9),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _FocusLanesPanel extends StatelessWidget {
  const _FocusLanesPanel({required this.tasks});

  final List<Map<String, dynamic>> tasks;

  int _count(String priority) {
    return tasks
        .where(
          (task) =>
              task['priority']?.toString().toLowerCase() ==
              priority.toLowerCase(),
        )
        .length;
  }

  @override
  Widget build(BuildContext context) {
    final critical = _count('high') + _count('critical');
    final growth = _count('medium');
    final maintenance = _count('low');
    final total = tasks.length;
    final focusTitle = total == 0
        ? 'No focus lanes yet'
        : 'Today’s focus signal';
    final focusBody = total == 0
        ? 'When AiPal helps you plan a task, reminder, commitment, or focus block, it will appear here without dummy agenda items.'
        : 'You have $total active agenda ${total == 1 ? 'item' : 'items'} across your lanes. Start with the highest-priority item, then come back for a lighter next step.';

    return _GlassPanel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Focus Lanes',
            style: TextStyle(
              fontFamily: 'Manrope',
              fontSize: 24,
              fontWeight: FontWeight.w800,
              color: Color(0xFF1B1C1A),
            ),
          ),
          const SizedBox(height: 24),
          _LaneBar(
            label: 'Critical',
            count: critical,
            color: const Color(0xFFBA1A1A),
            progress: critical == 0 ? 0.08 : 0.75,
            caption: 'Priority tasks',
          ),
          const SizedBox(height: 22),
          _LaneBar(
            label: 'Growth',
            count: growth,
            color: const Color(0xFFFFC815),
            progress: growth == 0 ? 0.08 : 0.45,
            caption: 'Deep work & progress',
          ),
          const SizedBox(height: 22),
          _LaneBar(
            label: 'Maintenance',
            count: maintenance,
            color: const Color(0xFF003B2B),
            progress: maintenance == 0 ? 0.08 : 0.55,
            caption: 'Admin & housekeeping',
          ),
          const SizedBox(height: 34),
          Container(
            padding: const EdgeInsets.all(18),
            decoration: BoxDecoration(
              color: const Color(0xFFFFF2B8).withValues(alpha: 0.38),
              borderRadius: BorderRadius.circular(24),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(
                  Icons.lightbulb_outline_rounded,
                  color: Color(0xFFFFC815),
                ),
                const SizedBox(height: 10),
                Text(
                  focusTitle,
                  style: const TextStyle(
                    fontWeight: FontWeight.w800,
                    color: Color(0xFFFFC815),
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  focusBody,
                  style: const TextStyle(
                    fontSize: 12.5,
                    height: 1.45,
                    color: Color(0xFF1B1C1A),
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

class _GlassPanel extends StatelessWidget {
  const _GlassPanel({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.45),
        borderRadius: BorderRadius.circular(32),
        border: Border.all(color: Colors.white.withValues(alpha: 0.75)),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF1A1F2C).withValues(alpha: 0.035),
            blurRadius: 48,
            offset: const Offset(0, 24),
          ),
        ],
      ),
      child: child,
    );
  }
}

class _TodayBackground extends StatelessWidget {
  const _TodayBackground();

  @override
  Widget build(BuildContext context) {
    final hour = DateTime.now().hour;
    final isEvening = hour >= 17 || hour < 5;
    final isMorning = hour >= 5 && hour < 12;
    final primary = isMorning
        ? const Color(0xFF003B2B)
        : isEvening
        ? const Color(0xFFFFC815)
        : const Color(0xFF4F6F8F);
    final secondary = isEvening
        ? const Color(0xFF003B2B)
        : const Color(0xFFFFC815);
    return Stack(
      children: [
        Container(color: const Color(0xFFFAF9F5)),
        Positioned(
          top: -180,
          right: -160,
          child: _BlurBlob(color: primary.withValues(alpha: 0.08)),
        ),
        Positioned(
          bottom: -200,
          left: -150,
          child: _BlurBlob(color: secondary.withValues(alpha: 0.08)),
        ),
      ],
    );
  }
}

class _PremiumBottomSheetShell extends StatelessWidget {
  const _PremiumBottomSheetShell({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: EdgeInsets.only(
          left: 16,
          right: 16,
          bottom: MediaQuery.of(context).viewInsets.bottom + 16,
        ),
        child: Container(
          constraints: const BoxConstraints(maxWidth: 560),
          padding: const EdgeInsets.fromLTRB(24, 12, 24, 24),
          decoration: BoxDecoration(
            color: const Color(0xFFFAF9F5),
            borderRadius: BorderRadius.circular(36),
            border: Border.all(color: const Color(0xFFE6E1D6)),
            boxShadow: [
              BoxShadow(
                color: const Color(0xFF1A1F2C).withValues(alpha: 0.12),
                blurRadius: 46,
                offset: const Offset(0, 24),
              ),
            ],
          ),
          child: SafeArea(top: false, child: child),
        ),
      ),
    );
  }
}

class _PremiumTaskSheet extends StatelessWidget {
  const _PremiumTaskSheet({
    required this.titleController,
    required this.noteController,
  });

  final TextEditingController titleController;
  final TextEditingController noteController;

  @override
  Widget build(BuildContext context) {
    return _PremiumBottomSheetShell(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const _SheetHandle(),
          const SizedBox(height: 20),
          const _SheetIcon(icon: Icons.add_task_rounded),
          const SizedBox(height: 16),
          const Text(
            'Add New Task',
            style: TextStyle(
              fontFamily: 'Manrope',
              fontSize: 28,
              fontWeight: FontWeight.w800,
              color: Color(0xFF1B1C1A),
            ),
          ),
          const SizedBox(height: 8),
          const Text(
            'Write what needs to be done. Keep it simple and clear.',
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: 14,
              height: 1.5,
              color: Color(0xFF1B1C1A),
            ),
          ),
          const SizedBox(height: 26),
          _PremiumInput(
            controller: titleController,
            hint: 'Task title',
            icon: Icons.task_alt_rounded,
            autofocus: true,
          ),
          const SizedBox(height: 14),
          _PremiumInput(
            controller: noteController,
            hint: 'Extra note, deadline, or context',
            icon: Icons.notes_rounded,
            maxLines: 3,
          ),
          const SizedBox(height: 24),
          _PremiumSheetButton(
            label: 'Create Task',
            icon: Icons.arrow_forward_rounded,
            onTap: () {
              Navigator.pop(context, <String, String>{
                'title': titleController.text.trim(),
                'notes': noteController.text.trim(),
              });
            },
          ),
        ],
      ),
    );
  }
}

class _SuggestPlanSheet extends StatelessWidget {
  const _SuggestPlanSheet();

  @override
  Widget build(BuildContext context) {
    return _PremiumBottomSheetShell(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const _SheetHandle(),
          const SizedBox(height: 20),
          const _SuggestSheetIcon(),
          const SizedBox(height: 16),
          const Text(
            'Suggest My Day',
            textAlign: TextAlign.center,
            style: TextStyle(
              fontFamily: 'Manrope',
              fontSize: 28,
              height: 1.15,
              fontWeight: FontWeight.w800,
              color: Color(0xFF1B1C1A),
            ),
          ),
          const SizedBox(height: 8),
          const Text(
            'Pick the starting shape for today and AiPal will build around it.',
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: 14,
              height: 1.55,
              fontWeight: FontWeight.w500,
              color: Color(0xFF4B444D),
            ),
          ),
          const SizedBox(height: 20),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(18),
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.72),
              borderRadius: BorderRadius.circular(28),
              border: Border.all(color: const Color(0xFFE6E1D6)),
              boxShadow: [
                BoxShadow(
                  color: const Color(0xFF1A1F2C).withValues(alpha: 0.03),
                  blurRadius: 26,
                  offset: const Offset(0, 12),
                ),
              ],
            ),
            child: const Column(
              children: [
                _SuggestOption(
                  title: 'Work Day',
                  subtitle: 'Meetings, follow-ups, admin, and practical tasks.',
                  icon: Icons.work_outline_rounded,
                  value: 'work',
                ),
                _SuggestOption(
                  title: 'Deep Work',
                  subtitle:
                      'Focused blocks for building, writing, coding, or planning.',
                  icon: Icons.psychology_rounded,
                  value: 'deep_work',
                ),
                _SuggestOption(
                  title: 'Balanced Day',
                  subtitle: 'Tasks, breaks, wellness, and a calmer pace.',
                  icon: Icons.spa_rounded,
                  value: 'wellness',
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _PremiumReviewSheet extends StatelessWidget {
  const _PremiumReviewSheet({
    required this.openTasks,
    required this.onDefer,
    required this.onGoLive,
  });

  final List<Map<String, dynamic>> openTasks;
  final VoidCallback onDefer;
  final VoidCallback onGoLive;

  @override
  Widget build(BuildContext context) {
    return _PremiumBottomSheetShell(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const _SheetHandle(),
          const SizedBox(height: 20),
          const _ReviewSheetIcon(),
          const SizedBox(height: 16),
          const Text(
            'Review Progress',
            textAlign: TextAlign.center,
            style: TextStyle(
              fontFamily: 'Manrope',
              fontSize: 28,
              height: 1.15,
              fontWeight: FontWeight.w800,
              color: Color(0xFF1B1C1A),
            ),
          ),
          const SizedBox(height: 8),
          Text(
            openTasks.isEmpty
                ? 'You are clear for now. No open tasks need review.'
                : '${openTasks.length} open task${openTasks.length == 1 ? '' : 's'} still need attention.',
            textAlign: TextAlign.center,
            style: const TextStyle(
              fontSize: 14,
              height: 1.55,
              fontWeight: FontWeight.w500,
              color: Color(0xFF1B1C1A),
            ),
          ),
          const SizedBox(height: 22),
          if (openTasks.isNotEmpty)
            ...openTasks
                .take(4)
                .map(
                  (task) => _ReviewTaskCard(
                    title: task['title']?.toString() ?? 'Untitled task',
                  ),
                ),
          const SizedBox(height: 20),
          _PremiumSheetButton(
            label: 'Talk Through My Day',
            icon: Icons.graphic_eq_rounded,
            onTap: onGoLive,
          ),
          const SizedBox(height: 10),
          OutlinedButton.icon(
            onPressed: onDefer,
            icon: const Icon(Icons.schedule_rounded),
            label: const Text('Defer Open Tasks'),
            style: OutlinedButton.styleFrom(
              foregroundColor: const Color(0xFFFFC815),
              side: const BorderSide(color: Color(0xFFE8DFAF)),
              minimumSize: const Size.fromHeight(52),
              shape: const StadiumBorder(),
              textStyle: const TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w800,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _PremiumInput extends StatelessWidget {
  const _PremiumInput({
    required this.controller,
    required this.hint,
    required this.icon,
    this.autofocus = false,
    this.maxLines = 1,
  });

  final TextEditingController controller;
  final String hint;
  final IconData icon;
  final bool autofocus;
  final int maxLines;

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: controller,
      autofocus: autofocus,
      maxLines: maxLines,
      style: const TextStyle(
        fontSize: 15,
        fontWeight: FontWeight.w600,
        color: Color(0xFF1B1C1A),
      ),
      decoration: InputDecoration(
        prefixIcon: Icon(icon, color: const Color(0xFFFFC815)),
        hintText: hint,
        hintStyle: const TextStyle(
          color: Color(0xFF1B1C1A),
          fontWeight: FontWeight.w500,
        ),
        filled: true,
        fillColor: Colors.white.withValues(alpha: 0.72),
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 20,
          vertical: 18,
        ),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(maxLines > 1 ? 24 : 999),
          borderSide: const BorderSide(color: Color(0xFFE8DFAF)),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(maxLines > 1 ? 24 : 999),
          borderSide: const BorderSide(color: Color(0xFFE8DFAF)),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(maxLines > 1 ? 24 : 999),
          borderSide: const BorderSide(color: Color(0xFFFFC815), width: 1.8),
        ),
      ),
    );
  }
}

class _SuggestOption extends StatelessWidget {
  const _SuggestOption({
    required this.title,
    required this.subtitle,
    required this.icon,
    required this.value,
  });

  final String title;
  final String subtitle;
  final IconData icon;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      borderRadius: BorderRadius.circular(24),
      child: InkWell(
        onTap: () => Navigator.pop(context, value),
        borderRadius: BorderRadius.circular(24),
        child: Container(
          margin: const EdgeInsets.only(bottom: 10),
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: const Color(0xFFFCFBF8),
            borderRadius: BorderRadius.circular(24),
            border: Border.all(color: const Color(0xFFE6E1D6)),
            boxShadow: [
              BoxShadow(
                color: const Color(0xFF1A1F2C).withValues(alpha: 0.03),
                blurRadius: 16,
                offset: const Offset(0, 8),
              ),
            ],
          ),
          child: Row(
            children: [
              _SmallOptionIcon(icon: icon),
              const SizedBox(width: 13),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      softWrap: true,
                      style: const TextStyle(
                        fontSize: 15.5,
                        height: 1.25,
                        fontWeight: FontWeight.w800,
                        color: Color(0xFF1B1C1A),
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      subtitle,
                      softWrap: true,
                      style: const TextStyle(
                        fontSize: 12.5,
                        height: 1.5,
                        fontWeight: FontWeight.w500,
                        color: Color(0xFF4B444D),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              const Icon(
                Icons.arrow_forward_rounded,
                size: 18,
                color: Color(0xFF575C6B),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ReviewTaskCard extends StatelessWidget {
  const _ReviewTaskCard({required this.title});

  final String title;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFFFBFAF7),
        borderRadius: BorderRadius.circular(22),
        border: Border.all(color: const Color(0xFFE6E1D6)),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF1A1F2C).withValues(alpha: 0.03),
            blurRadius: 18,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: Row(
        children: [
          const Icon(
            Icons.radio_button_unchecked_rounded,
            size: 18,
            color: Color(0xFFFFC815),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              title,
              style: const TextStyle(
                fontSize: 14,
                height: 1.35,
                fontWeight: FontWeight.w800,
                color: Color(0xFF1B1C1A),
              ),
            ),
          ),
        ],
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

class _ReviewSheetIcon extends StatelessWidget {
  const _ReviewSheetIcon();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 56,
      height: 56,
      decoration: BoxDecoration(
        color: const Color(0xFFF6F2EA),
        shape: BoxShape.circle,
        border: Border.all(color: const Color(0xFFE6E1D6)),
      ),
      child: const Icon(
        Icons.history_edu_rounded,
        color: Color(0xFFFFC815),
        size: 26,
      ),
    );
  }
}

class _SheetIcon extends StatelessWidget {
  const _SheetIcon({required this.icon});

  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 56,
      height: 56,
      decoration: const BoxDecoration(
        shape: BoxShape.circle,
        gradient: LinearGradient(
          colors: [Color(0xFFFFC815), Color(0xFF003B2B)],
        ),
      ),
      child: Icon(icon, color: Colors.white, size: 26),
    );
  }
}

class _SuggestSheetIcon extends StatelessWidget {
  const _SuggestSheetIcon();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 56,
      height: 56,
      decoration: BoxDecoration(
        color: const Color(0xFFF6F2EA),
        shape: BoxShape.circle,
        border: Border.all(color: const Color(0xFFE6E1D6)),
      ),
      child: const Icon(
        Icons.auto_awesome_rounded,
        color: Color(0xFFFFC815),
        size: 26,
      ),
    );
  }
}

class _SmallOptionIcon extends StatelessWidget {
  const _SmallOptionIcon({required this.icon});

  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 44,
      height: 44,
      decoration: BoxDecoration(
        color: const Color(0xFFF8F7F3),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFFE6E1D6)),
      ),
      child: Icon(icon, color: const Color(0xFFFFC815), size: 22),
    );
  }
}

class _PremiumSheetButton extends StatelessWidget {
  const _PremiumSheetButton({
    required this.label,
    required this.icon,
    required this.onTap,
  });

  final String label;
  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return FilledButton.icon(
      onPressed: onTap,
      icon: Icon(icon, size: 19),
      label: Text(label, overflow: TextOverflow.ellipsis),
      style: FilledButton.styleFrom(
        backgroundColor: const Color(0xFFFFC815),
        foregroundColor: Colors.white,
        minimumSize: const Size.fromHeight(54),
        shape: const StadiumBorder(),
        textStyle: const TextStyle(
          fontSize: 14,
          fontWeight: FontWeight.w800,
          letterSpacing: 0.08,
        ),
      ),
    );
  }
}

class _BlurBlob extends StatelessWidget {
  const _BlurBlob({required this.color});

  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 520,
      height: 520,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        boxShadow: [BoxShadow(color: color, blurRadius: 130, spreadRadius: 70)],
      ),
    );
  }
}

class _MiniStat extends StatelessWidget {
  const _MiniStat({
    required this.value,
    required this.label,
    required this.icon,
  });

  final String value;
  final String label;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 16, color: const Color(0xFFFFC815)),
        const SizedBox(width: 6),
        Text(
          value,
          style: const TextStyle(
            color: Color(0xFFFFC815),
            fontWeight: FontWeight.w900,
          ),
        ),
        const SizedBox(width: 5),
        Text(
          label,
          style: const TextStyle(
            color: Color(0xFF1B1C1A),
            fontWeight: FontWeight.w500,
          ),
        ),
      ],
    );
  }
}

class _ChipButton extends StatelessWidget {
  const _ChipButton({required this.label, required this.onTap});

  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return OutlinedButton(
      onPressed: onTap,
      style: OutlinedButton.styleFrom(
        foregroundColor: const Color(0xFF1B1C1A),
        side: BorderSide(
          color: const Color(0xFFE8DFAF).withValues(alpha: 0.62),
        ),
        backgroundColor: const Color(0xFFF8F7F3),
        shape: const StadiumBorder(),
        minimumSize: const Size(0, 48),
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
        textStyle: const TextStyle(fontSize: 13.5, fontWeight: FontWeight.w700),
      ),
      child: Text(label),
    );
  }
}

class _GradientChip extends StatelessWidget {
  const _GradientChip({
    required this.busy,
    required this.label,
    required this.onTap,
  });

  final bool busy;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [Color(0xFFFFC815), Color(0xFFE8A838)],
        ),
        borderRadius: BorderRadius.circular(999),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFFFFC815).withValues(alpha: 0.18),
            blurRadius: 20,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: TextButton.icon(
        onPressed: busy ? null : onTap,
        icon: busy
            ? const SizedBox(
                width: 15,
                height: 15,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  color: Colors.white,
                ),
              )
            : const Icon(Icons.auto_awesome_rounded, size: 17),
        label: Text(label),
        style: TextButton.styleFrom(
          foregroundColor: Colors.white,
          minimumSize: const Size(0, 48),
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
          textStyle: const TextStyle(
            fontSize: 13.5,
            fontWeight: FontWeight.w700,
          ),
        ),
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader({required this.title, required this.count});

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
            fontSize: 24,
            fontWeight: FontWeight.w800,
            color: Color(0xFF1B1C1A),
          ),
        ),
        const Spacer(),
        Text(
          '$count tasks',
          style: const TextStyle(
            color: Color(0xFF1B1C1A),
            fontWeight: FontWeight.w600,
          ),
        ),
      ],
    );
  }
}

class _PriorityPill extends StatelessWidget {
  const _PriorityPill({
    required this.label,
    required this.color,
    required this.background,
  });

  final String label;
  final Color color;
  final Color background;

  @override
  Widget build(BuildContext context) {
    final normalized = label.isEmpty
        ? 'Medium'
        : '${label[0].toUpperCase()}${label.substring(1)}';

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: background.withValues(alpha: 0.55),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        normalized,
        style: TextStyle(
          fontSize: 10,
          fontWeight: FontWeight.w900,
          letterSpacing: 0.6,
          color: color,
        ),
      ),
    );
  }
}

class _PrimaryActionButton extends StatelessWidget {
  const _PrimaryActionButton({
    required this.icon,
    required this.label,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return FilledButton.icon(
      onPressed: onTap,
      icon: Icon(icon),
      label: Text(label),
      style: FilledButton.styleFrom(
        backgroundColor: const Color(0xFFFFC815),
        foregroundColor: Colors.white,
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 13),
      ),
    );
  }
}

class _GlassButton extends StatelessWidget {
  const _GlassButton({
    required this.icon,
    required this.label,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return OutlinedButton.icon(
      onPressed: onTap,
      icon: Icon(icon, size: 18),
      label: Text(label),
      style: OutlinedButton.styleFrom(
        foregroundColor: const Color(0xFFFFC815),
        backgroundColor: Colors.white.withValues(alpha: 0.45),
        side: BorderSide(color: Colors.white.withValues(alpha: 0.8)),
        shape: const StadiumBorder(),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      ),
    );
  }
}

class _LaneBar extends StatelessWidget {
  const _LaneBar({
    required this.label,
    required this.count,
    required this.color,
    required this.progress,
    required this.caption,
  });

  final String label;
  final int count;
  final Color color;
  final double progress;
  final String caption;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Text(
              label.toUpperCase(),
              style: TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w900,
                letterSpacing: 0.8,
                color: color,
              ),
            ),
            const Spacer(),
            Text(
              '$count',
              style: const TextStyle(
                color: Color(0xFF1B1C1A),
                fontWeight: FontWeight.w700,
              ),
            ),
          ],
        ),
        const SizedBox(height: 9),
        ClipRRect(
          borderRadius: BorderRadius.circular(999),
          child: LinearProgressIndicator(
            value: progress.clamp(0, 1),
            minHeight: 5,
            backgroundColor: const Color(0xFFEFEFEA),
            valueColor: AlwaysStoppedAnimation<Color>(color),
          ),
        ),
        const SizedBox(height: 7),
        Text(
          caption,
          style: const TextStyle(
            fontSize: 12,
            fontStyle: FontStyle.italic,
            color: Color(0xFF1B1C1A),
          ),
        ),
      ],
    );
  }
}

class _EmptyGlassMessage extends StatelessWidget {
  const _EmptyGlassMessage();

  @override
  Widget build(BuildContext context) {
    return const _GlassPanel(
      child: Text(
        'No upcoming tasks yet. Ask AiPal to suggest a plan for your day.',
        style: TextStyle(
          fontSize: 15,
          height: 1.5,
          fontWeight: FontWeight.w500,
          color: Color(0xFF4B444D),
        ),
      ),
    );
  }
}
