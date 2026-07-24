import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/app_state.dart';
import 'notifications_screen.dart';
import 'companion_screen.dart';
import 'settings_screen.dart';
import 'task_detail_screen.dart';
import 'text_chat_screen.dart';
import 'today_screen.dart';

class HomeShell extends StatelessWidget {
  const HomeShell({super.key});

  static const _tabs = [
    CompanionScreen(),
    TodayScreen(),
    NotificationsScreen(),
    SettingsScreen(),
  ];

  static const _titles = ['Companion', 'Today', 'Notifications', 'Settings'];

  static const _subtitles = [
    "What's on your mind today?",
    'Your plan, tasks, and reminders',
    'Updates, reminders and calendar activity',
    'Manage your AiPal experience',
  ];

  @override
  Widget build(BuildContext context) {
    final index = context.watch<AppState>().selectedTab;
    return AiPalShellScaffold(
      title: _titles[index],
      subtitle: _subtitles[index],
      onNotificationsTap: () => context.read<AppState>().goToTab(2),
      onProfileTap: () => context.read<AppState>().goToTab(3),
      body: IndexedStack(index: index, children: _tabs),
    );
  }
}

class AiPalShellScaffold extends StatelessWidget {
  const AiPalShellScaffold({
    super.key,
    required this.title,
    required this.subtitle,
    required this.body,
    required this.onNotificationsTap,
    required this.onProfileTap,
    this.onSidebarTabTap,
    this.activeSidebarIndex,
    this.showDesktopSidebar = true,
    this.showMobileBottomNav = true,
  });

  final String title;
  final String subtitle;
  final Widget body;
  final VoidCallback onNotificationsTap;
  final VoidCallback onProfileTap;
  final ValueChanged<int>? onSidebarTabTap;
  final int? activeSidebarIndex;
  final bool showDesktopSidebar;
  final bool showMobileBottomNav;

  @override
  Widget build(BuildContext context) {
    final isDesktop = MediaQuery.of(context).size.width >= 900;
    final activeIndex =
        activeSidebarIndex ?? context.watch<AppState>().selectedTab;
    final tabTap =
        onSidebarTabTap ??
        (int index) => context.read<AppState>().goToTab(index);

    return Scaffold(
      backgroundColor: const Color(0xFFFAF9F5),
      body: Row(
        children: [
          if (isDesktop && showDesktopSidebar)
            _DesktopSidebar(activeIndex: activeIndex, onTabTap: tabTap),
          Expanded(
            child: Column(
              children: [
                _TopHeader(
                  title: title,
                  subtitle: subtitle,
                  onNotificationsTap: onNotificationsTap,
                  onProfileTap: onProfileTap,
                ),
                Expanded(child: body),
              ],
            ),
          ),
        ],
      ),
      bottomNavigationBar: isDesktop || !showMobileBottomNav
          ? null
          : _MobileBottomNav(currentIndex: activeIndex, onTabTap: tabTap),
    );
  }
}

class _DesktopSidebar extends StatefulWidget {
  const _DesktopSidebar({required this.activeIndex, required this.onTabTap});

  final int activeIndex;
  final ValueChanged<int> onTabTap;

  @override
  State<_DesktopSidebar> createState() => _DesktopSidebarState();
}

class _DesktopSidebarState extends State<_DesktopSidebar> {
  bool _companionOpen = true;
  bool _todayOpen = true;

  Future<void> _confirmDeleteConversation(
    BuildContext context,
    AppState state,
    String sessionId,
  ) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete conversation?'),
        content: const Text(
          'This will remove the conversation thread from the sidebar.',
        ),
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
    if (ok == true && mounted) {
      await state.deleteConversationSession(sessionId);
    }
  }

  Future<void> _editTask(
    BuildContext context,
    AppState state,
    Map<String, dynamic> task,
  ) async {
    final titleController = TextEditingController(
      text: task['title']?.toString() ?? '',
    );
    final notesController = TextEditingController(
      text: task['notes']?.toString() ?? '',
    );
    final result = await showModalBottomSheet<Map<String, String>>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _TaskEditorSheet(
        titleController: titleController,
        notesController: notesController,
      ),
    );
    titleController.dispose();
    notesController.dispose();
    if (result != null && mounted) {
      await state.updateTask(
        task['id'] as int,
        title: result['title']?.trim(),
        notes: result['notes']?.trim(),
      );
    }
  }

  void _openTaskDetail(BuildContext context, Map<String, dynamic> task) {
    final taskId = task['id']?.toString();
    if (taskId == null || taskId.isEmpty) return;
    Navigator.of(
      context,
    ).push(MaterialPageRoute(builder: (_) => TaskDetailScreen(taskId: taskId)));
  }

  @override
  Widget build(BuildContext context) {
    final index = widget.activeIndex;
    final state = context.watch<AppState>();
    final sections = state.todayView?['sections'] as Map<String, dynamic>?;
    final companionSessions = state.conversationSessions;
    final openTasks = state.openTasksForReview.isNotEmpty
        ? state.openTasksForReview
        : [
            ...((sections?['now'] as List?)?.cast<Map<String, dynamic>>() ??
                []),
            ...((sections?['upcoming'] as List?)
                    ?.cast<Map<String, dynamic>>() ??
                []),
          ];

    return Container(
      width: 256,
      height: double.infinity,
      decoration: BoxDecoration(
        color: const Color(0xFFFAF9F5).withValues(alpha: 0.72),
        border: Border(
          right: BorderSide(color: Colors.white.withValues(alpha: 0.7)),
        ),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF1A1F2C).withValues(alpha: 0.04),
            blurRadius: 60,
            offset: const Offset(30, 0),
          ),
        ],
      ),
      child: SafeArea(
        bottom: false,
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const SizedBox(height: 8),
              const Text(
                'AiPal',
                style: TextStyle(
                  fontFamily: 'Manrope',
                  fontSize: 42,
                  height: 1,
                  fontWeight: FontWeight.w800,
                  letterSpacing: -1.4,
                  color: Color(0xFFFFC815),
                ),
              ),
              const SizedBox(height: 8),
              const Text(
                'Quiet Intelligence',
                style: TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                  color: Color(0xFF575C6B),
                ),
              ),
              const SizedBox(height: 28),

              _SidebarItem(
                index: 0,
                currentIndex: index,
                icon: Icons.graphic_eq_rounded,
                label: 'Companion',
                onTap: widget.onTabTap,
              ),
              const SizedBox(height: 12),
              _SidebarItem(
                index: 1,
                currentIndex: index,
                icon: Icons.calendar_today_rounded,
                label: 'Today',
                onTap: widget.onTabTap,
              ),
              const SizedBox(height: 12),
              _SidebarItem(
                index: 2,
                currentIndex: index,
                icon: Icons.notifications_none_rounded,
                label: 'Notifications',
                onTap: widget.onTabTap,
              ),
              const SizedBox(height: 12),
              _SidebarItem(
                index: 3,
                currentIndex: index,
                icon: Icons.settings_rounded,
                label: 'Settings',
                onTap: widget.onTabTap,
              ),

              const SizedBox(height: 18),
              if (index == 0)
                _SidebarAccordion(
                  title: 'Companion threads',
                  subtitle: 'Resume or remove a conversation',
                  expanded: _companionOpen,
                  onChanged: (v) => setState(() => _companionOpen = v),
                  child: companionSessions.isEmpty
                      ? const _SidebarEmptyHint(
                          text: 'No saved conversations yet.',
                        )
                      : Column(
                          children: companionSessions.map((session) {
                            final sessionId =
                                session['session_id']?.toString() ?? '';
                            return _ThreadTile(
                              title:
                                  session['preview']?.toString().isNotEmpty ==
                                      true
                                  ? session['preview'].toString()
                                  : 'Conversation',
                              meta:
                                  '${session['turn_count']?.toString() ?? '0'} turns',
                              onOpen: () {
                                Navigator.of(context).push(
                                  MaterialPageRoute(
                                    builder: (_) =>
                                        TextChatScreen(sessionId: sessionId),
                                  ),
                                );
                              },
                              onDelete: () => _confirmDeleteConversation(
                                context,
                                state,
                                sessionId,
                              ),
                            );
                          }).toList(),
                        ),
                ),
              if (index == 1)
                _SidebarAccordion(
                  title: 'Today tasks',
                  subtitle: 'Edit or delete open work',
                  expanded: _todayOpen,
                  onChanged: (v) => setState(() => _todayOpen = v),
                  child: openTasks.isEmpty
                      ? const _SidebarEmptyHint(
                          text: 'No open tasks to edit right now.',
                        )
                      : Column(
                          children: openTasks.take(8).map((task) {
                            return _TaskTile(
                              title:
                                  task['title']?.toString() ?? 'Untitled task',
                              meta:
                                  task['due_label']?.toString() ??
                                  task['status']?.toString() ??
                                  'planned',
                              onOpen: () => _openTaskDetail(context, task),
                              onEdit: () => _editTask(context, state, task),
                              onDelete: () async {
                                final id = task['id'] as int?;
                                if (id != null) {
                                  final messenger = ScaffoldMessenger.of(
                                    context,
                                  );
                                  await state.deleteTask(id);
                                  if (mounted) {
                                    messenger.showSnackBar(
                                      const SnackBar(
                                        content: Text('Task deleted'),
                                      ),
                                    );
                                  }
                                }
                              },
                            );
                          }).toList(),
                        ),
                ),

              const SizedBox(height: 20),

              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.45),
                  borderRadius: BorderRadius.circular(24),
                  border: Border.all(
                    color: Colors.white.withValues(alpha: 0.7),
                  ),
                ),
                child: Row(
                  children: [
                    Container(
                      width: 42,
                      height: 42,
                      decoration: const BoxDecoration(
                        shape: BoxShape.circle,
                        gradient: LinearGradient(
                          colors: [Color(0xFFFFC815), Color(0xFF003B2B)],
                        ),
                      ),
                      child: const Icon(
                        Icons.person_rounded,
                        color: Colors.white,
                      ),
                    ),
                    const SizedBox(width: 12),
                    const Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Kelvin',
                            style: TextStyle(
                              fontSize: 14,
                              fontWeight: FontWeight.w800,
                              color: Color(0xFF1B1C1A),
                            ),
                          ),
                          SizedBox(height: 2),
                          Text(
                            'Premium Plan',
                            style: TextStyle(
                              fontSize: 10,
                              fontWeight: FontWeight.w700,
                              letterSpacing: 0.8,
                              color: Color(0xFF575C6B),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SidebarItem extends StatelessWidget {
  const _SidebarItem({
    required this.index,
    required this.currentIndex,
    required this.icon,
    required this.label,
    required this.onTap,
  });

  final int index;
  final int currentIndex;
  final IconData icon;
  final String label;
  final ValueChanged<int> onTap;

  @override
  Widget build(BuildContext context) {
    final active = index == currentIndex;

    return Material(
      color: active
          ? const Color(0xFFFFF2B8).withValues(alpha: 0.55)
          : Colors.transparent,
      borderRadius: BorderRadius.circular(24),
      child: InkWell(
        borderRadius: BorderRadius.circular(24),
        onTap: () => onTap(index),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 13),
          child: Row(
            children: [
              Icon(
                icon,
                color: active
                    ? const Color(0xFFFFC815)
                    : const Color(0xFF575C6B),
              ),
              const SizedBox(width: 14),
              Text(
                label,
                style: TextStyle(
                  fontSize: 14,
                  fontWeight: active ? FontWeight.w800 : FontWeight.w600,
                  color: active
                      ? const Color(0xFFFFC815)
                      : const Color(0xFF575C6B),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SidebarAccordion extends StatelessWidget {
  const _SidebarAccordion({
    required this.title,
    required this.subtitle,
    required this.expanded,
    required this.onChanged,
    required this.child,
  });

  final String title;
  final String subtitle;
  final bool expanded;
  final ValueChanged<bool> onChanged;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Theme(
      data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
      child: Material(
        color: Colors.transparent,
        child: ExpansionTile(
          initiallyExpanded: expanded,
          onExpansionChanged: onChanged,
          tilePadding: EdgeInsets.zero,
          childrenPadding: const EdgeInsets.only(top: 10),
          collapsedIconColor: const Color(0xFFFFC815),
          iconColor: const Color(0xFFFFC815),
          title: Text(
            title,
            style: const TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w800,
              letterSpacing: 0.6,
              color: Color(0xFF1B1C1A),
            ),
          ),
          subtitle: Text(
            subtitle,
            style: const TextStyle(
              fontSize: 11.5,
              height: 1.35,
              color: Color(0xFF575C6B),
            ),
          ),
          children: [child],
        ),
      ),
    );
  }
}

class _SidebarEmptyHint extends StatelessWidget {
  const _SidebarEmptyHint({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.48),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: Colors.white.withValues(alpha: 0.75)),
      ),
      child: Text(
        text,
        style: const TextStyle(
          fontSize: 12.5,
          height: 1.45,
          color: Color(0xFF575C6B),
        ),
      ),
    );
  }
}

class _ThreadTile extends StatelessWidget {
  const _ThreadTile({
    required this.title,
    required this.meta,
    required this.onOpen,
    required this.onDelete,
  });

  final String title;
  final String meta;
  final VoidCallback onOpen;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.5),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: Colors.white.withValues(alpha: 0.78)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              fontSize: 13.5,
              height: 1.3,
              fontWeight: FontWeight.w800,
              color: Color(0xFF1B1C1A),
            ),
          ),
          const SizedBox(height: 6),
          Text(
            meta,
            style: const TextStyle(fontSize: 11.5, color: Color(0xFF575C6B)),
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              TextButton(onPressed: onOpen, child: const Text('Return')),
              const Spacer(),
              IconButton(
                onPressed: onDelete,
                icon: const Icon(Icons.delete_outline_rounded),
                color: const Color(0xFFBA1A1A),
                tooltip: 'Delete conversation',
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _TaskTile extends StatelessWidget {
  const _TaskTile({
    required this.title,
    required this.meta,
    required this.onOpen,
    required this.onEdit,
    required this.onDelete,
  });

  final String title;
  final String meta;
  final VoidCallback onOpen;
  final VoidCallback onEdit;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.white.withValues(alpha: 0.5),
      borderRadius: BorderRadius.circular(20),
      child: InkWell(
        borderRadius: BorderRadius.circular(20),
        onTap: onOpen,
        child: Container(
          margin: const EdgeInsets.only(bottom: 10),
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(20),
            border: Border.all(color: Colors.white.withValues(alpha: 0.78)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  fontSize: 13.5,
                  height: 1.3,
                  fontWeight: FontWeight.w800,
                  color: Color(0xFF1B1C1A),
                ),
              ),
              const SizedBox(height: 6),
              Text(
                meta,
                style: const TextStyle(
                  fontSize: 11.5,
                  color: Color(0xFF575C6B),
                ),
              ),
              const SizedBox(height: 8),
              Row(
                children: [
                  TextButton(onPressed: onEdit, child: const Text('Edit')),
                  const Spacer(),
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 8,
                      vertical: 4,
                    ),
                    decoration: BoxDecoration(
                      color: const Color(0xFFFFF2B8).withValues(alpha: 0.45),
                      borderRadius: BorderRadius.circular(999),
                    ),
                    child: const Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          'Open',
                          style: TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w800,
                            color: Color(0xFFFFC815),
                          ),
                        ),
                        SizedBox(width: 4),
                        Icon(
                          Icons.chevron_right_rounded,
                          size: 16,
                          color: Color(0xFFFFC815),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(width: 8),
                  IconButton(
                    onPressed: onDelete,
                    icon: const Icon(Icons.delete_outline_rounded),
                    color: const Color(0xFFBA1A1A),
                    tooltip: 'Delete task',
                  ),
                ],
              ),
            ],
          ),
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

class _TaskEditorSheet extends StatelessWidget {
  const _TaskEditorSheet({
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
        constraints: const BoxConstraints(maxWidth: 560),
        padding: const EdgeInsets.fromLTRB(24, 12, 24, 24),
        decoration: BoxDecoration(
          color: const Color(0xFFFAF9F5),
          borderRadius: BorderRadius.circular(36),
          border: Border.all(color: Colors.white.withValues(alpha: 0.9)),
          boxShadow: [
            BoxShadow(
              color: const Color(0xFFFFC815).withValues(alpha: 0.12),
              blurRadius: 50,
              offset: const Offset(0, 24),
            ),
          ],
        ),
        child: SafeArea(
          top: false,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const _SheetHandle(),
              const SizedBox(height: 20),
              Container(
                width: 56,
                height: 56,
                decoration: BoxDecoration(
                  color: const Color(0xFFFFF2B8),
                  shape: BoxShape.circle,
                  border: Border.all(color: const Color(0xFFE6E1D6)),
                ),
                child: const Icon(
                  Icons.edit_note_rounded,
                  color: Color(0xFFFFC815),
                  size: 28,
                ),
              ),
              const SizedBox(height: 16),
              const Text(
                'Edit Task',
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
                'Update the task details and keep the rhythm clear.',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 14,
                  height: 1.55,
                  fontWeight: FontWeight.w500,
                  color: Color(0xFF4B444D),
                ),
              ),
              const SizedBox(height: 22),
              _EditorInput(
                controller: titleController,
                hint: 'Task title',
                icon: Icons.task_alt_rounded,
                autofocus: true,
              ),
              const SizedBox(height: 14),
              _EditorInput(
                controller: notesController,
                hint: 'Notes or context',
                icon: Icons.notes_rounded,
                maxLines: 3,
              ),
              const SizedBox(height: 22),
              FilledButton.icon(
                onPressed: () {
                  Navigator.pop(context, <String, String>{
                    'title': titleController.text.trim(),
                    'notes': notesController.text.trim(),
                  });
                },
                icon: const Icon(Icons.check_rounded, size: 18),
                label: const Text('Save Changes'),
                style: FilledButton.styleFrom(
                  backgroundColor: const Color(0xFFFFC815),
                  foregroundColor: Colors.white,
                  minimumSize: const Size.fromHeight(52),
                  shape: const StadiumBorder(),
                  textStyle: const TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 0.08,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _EditorInput extends StatelessWidget {
  const _EditorInput({
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
          color: Color(0xFF4B444D),
          fontWeight: FontWeight.w500,
        ),
        filled: true,
        fillColor: Colors.white,
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 20,
          vertical: 18,
        ),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(maxLines > 1 ? 24 : 999),
          borderSide: const BorderSide(color: Color(0xFFE8DFAF), width: 1.2),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(maxLines > 1 ? 24 : 999),
          borderSide: const BorderSide(color: Color(0xFFE8DFAF), width: 1.2),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(maxLines > 1 ? 24 : 999),
          borderSide: const BorderSide(color: Color(0xFFFFC815), width: 1.8),
        ),
      ),
    );
  }
}

class _TopHeader extends StatelessWidget {
  const _TopHeader({
    required this.title,
    required this.subtitle,
    required this.onNotificationsTap,
    required this.onProfileTap,
  });

  final String title;
  final String subtitle;
  final VoidCallback onNotificationsTap;
  final VoidCallback onProfileTap;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      bottom: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(24, 18, 24, 14),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title == 'Companion' ? 'Good Afternoon, Kelvin' : title,
                    style: const TextStyle(
                      fontFamily: 'Manrope',
                      fontSize: 28,
                      height: 1.15,
                      fontWeight: FontWeight.w800,
                      letterSpacing: -0.6,
                      color: Color(0xFF1B1C1A),
                    ),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    subtitle,
                    style: const TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.w500,
                      color: Color(0xFF575C6B),
                    ),
                  ),
                ],
              ),
            ),
            _HeaderIconButton(
              icon: Icons.notifications_none_rounded,
              onTap: onNotificationsTap,
            ),
            const SizedBox(width: 12),
            _HeaderIconButton(
              icon: Icons.account_circle_rounded,
              onTap: onProfileTap,
            ),
          ],
        ),
      ),
    );
  }
}

class _HeaderIconButton extends StatelessWidget {
  const _HeaderIconButton({required this.icon, required this.onTap});

  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.white.withValues(alpha: 0.5),
      shape: const CircleBorder(),
      child: InkWell(
        customBorder: const CircleBorder(),
        onTap: onTap,
        child: Container(
          width: 48,
          height: 48,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            border: Border.all(color: Colors.white.withValues(alpha: 0.8)),
          ),
          child: Icon(icon, color: const Color(0xFF4B444D)),
        ),
      ),
    );
  }
}

class _MobileBottomNav extends StatelessWidget {
  const _MobileBottomNav({required this.currentIndex, required this.onTabTap});

  final int currentIndex;
  final ValueChanged<int> onTabTap;

  @override
  Widget build(BuildContext context) {
    final index = currentIndex;

    return Container(
      padding: const EdgeInsets.fromLTRB(20, 10, 20, 18),
      decoration: BoxDecoration(
        color: const Color(0xFFFAF9F5).withValues(alpha: 0.9),
        border: Border(
          top: BorderSide(color: Colors.white.withValues(alpha: 0.7)),
        ),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF1A1F2C).withValues(alpha: 0.05),
            blurRadius: 40,
            offset: const Offset(0, -10),
          ),
        ],
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceAround,
        children: [
          _MobileNavItem(
            index: 0,
            currentIndex: index,
            icon: Icons.graphic_eq_rounded,
            label: 'Companion',
            onTap: onTabTap,
          ),
          _MobileNavItem(
            index: 1,
            currentIndex: index,
            icon: Icons.calendar_today_rounded,
            label: 'Today',
            onTap: onTabTap,
          ),
          _MobileNavItem(
            index: 2,
            currentIndex: index,
            icon: Icons.notifications_none_rounded,
            label: 'Notifications',
            onTap: onTabTap,
          ),
          _MobileNavItem(
            index: 3,
            currentIndex: index,
            icon: Icons.settings_rounded,
            label: 'Settings',
            onTap: onTabTap,
          ),
        ],
      ),
    );
  }
}

class _MobileNavItem extends StatelessWidget {
  const _MobileNavItem({
    required this.index,
    required this.currentIndex,
    required this.icon,
    required this.label,
    required this.onTap,
  });

  final int index;
  final int currentIndex;
  final IconData icon;
  final String label;
  final ValueChanged<int> onTap;

  @override
  Widget build(BuildContext context) {
    final active = index == currentIndex;

    return InkWell(
      borderRadius: BorderRadius.circular(999),
      onTap: () => onTap(index),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 220),
        padding: EdgeInsets.symmetric(
          horizontal: active ? 16 : 10,
          vertical: 8,
        ),
        decoration: BoxDecoration(
          color: active
              ? const Color(0xFFFFF2B8).withValues(alpha: 0.65)
              : Colors.transparent,
          borderRadius: BorderRadius.circular(999),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              icon,
              color: active ? const Color(0xFFFFC815) : const Color(0xFF4B444D),
            ),
            const SizedBox(height: 3),
            Text(
              label,
              style: TextStyle(
                fontSize: 11,
                fontWeight: active ? FontWeight.w800 : FontWeight.w600,
                color: active
                    ? const Color(0xFF583B6B)
                    : const Color(0xFF4B444D),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
