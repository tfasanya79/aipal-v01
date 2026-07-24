import 'package:flutter/material.dart';

import 'task_category.dart';

const Color _focusReadyAccent = Color(0xFFFFC815);

class UpNextCard extends StatelessWidget {
  const UpNextCard({
    super.key,
    required this.task,
    this.onStartFocus,
    this.onDone,
    this.onBreakdown,
  });

  final Map<String, dynamic> task;
  final VoidCallback? onStartFocus;
  final VoidCallback? onDone;
  final VoidCallback? onBreakdown;

  @override
  Widget build(BuildContext context) {
    final subs =
        (task['subtasks'] as List?)?.cast<Map<String, dynamic>>() ?? [];
    final accent = categoryColor(task['category'] as String?);
    final est = formatEstimate(task['estimated_minutes'] as int?);
    final title = task['title']?.toString() ?? 'Untitled task';

    return Container(
      width: double.infinity,
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      padding: const EdgeInsets.all(1.4),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(34),
        gradient: LinearGradient(
          colors: [
            const Color(0xFFFFC815).withValues(alpha: 0.22),
            const Color(0xFF003B2B).withValues(alpha: 0.14),
          ],
        ),
      ),
      child: Container(
        padding: const EdgeInsets.all(22),
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.72),
          borderRadius: BorderRadius.circular(33),
          border: Border.all(color: Colors.white.withValues(alpha: 0.9)),
          boxShadow: [
            BoxShadow(
              color: const Color(0xFF1A1F2C).withValues(alpha: 0.05),
              blurRadius: 38,
              offset: const Offset(0, 20),
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _CardHeader(accent: accent),
            const SizedBox(height: 18),

            Text(
              title,
              softWrap: true,
              style: const TextStyle(
                fontFamily: 'Manrope',
                fontSize: 24,
                height: 1.22,
                fontWeight: FontWeight.w900,
                letterSpacing: -0.35,
                color: Color(0xFF1B1C1A),
              ),
            ),

            const SizedBox(height: 16),

            Wrap(
              spacing: 10,
              runSpacing: 10,
              children: [
                if (est.isNotEmpty)
                  _MetaChip(
                    icon: Icons.schedule_rounded,
                    label: est,
                    accent: accent,
                  ),
                const _MetaChip(
                  icon: Icons.bolt_rounded,
                  label: 'Focus ready',
                  accent: _focusReadyAccent,
                ),
              ],
            ),

            if (subs.isNotEmpty) ...[
              const SizedBox(height: 18),
              _SubtasksPreview(subtasks: subs),
            ],

            const SizedBox(height: 22),

            Row(
              children: [
                Expanded(
                  child: FilledButton.icon(
                    onPressed: onStartFocus,
                    icon: const Icon(Icons.play_arrow_rounded, size: 20),
                    label: const Text('Start Focus'),
                    style: FilledButton.styleFrom(
                      backgroundColor: const Color(0xFFFFC815),
                      foregroundColor: Colors.white,
                      minimumSize: const Size.fromHeight(52),
                      shape: const StadiumBorder(),
                      textStyle: const TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 10),
                _RoundActionButton(
                  icon: Icons.done_rounded,
                  tooltip: 'Done',
                  onTap: onDone,
                ),
                if (subs.isEmpty && onBreakdown != null) ...[
                  const SizedBox(width: 10),
                  _RoundActionButton(
                    icon: Icons.account_tree_rounded,
                    tooltip: 'Break down',
                    onTap: onBreakdown,
                  ),
                ],
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _CardHeader extends StatelessWidget {
  const _CardHeader({required this.accent});

  final Color accent;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Container(
          width: 42,
          height: 42,
          decoration: BoxDecoration(
            color: accent.withValues(alpha: 0.12),
            borderRadius: BorderRadius.circular(16),
          ),
          child: Icon(Icons.flag_rounded, color: accent, size: 22),
        ),
        const SizedBox(width: 12),
        const Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'UP NEXT',
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w900,
                  letterSpacing: 1.4,
                  color: Color(0xFFFFC815),
                ),
              ),
              SizedBox(height: 3),
              Text(
                'Your next best action',
                style: TextStyle(
                  fontSize: 12.5,
                  fontWeight: FontWeight.w600,
                  color: Color(0xFF4B444D),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _MetaChip extends StatelessWidget {
  const _MetaChip({
    required this.icon,
    required this.label,
    required this.accent,
  });

  final IconData icon;
  final String label;
  final Color accent;

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
          Icon(icon, size: 17, color: accent),
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

class _SubtasksPreview extends StatelessWidget {
  const _SubtasksPreview({required this.subtasks});

  final List<Map<String, dynamic>> subtasks;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFFF8F7F3),
        borderRadius: BorderRadius.circular(22),
        border: Border.all(color: const Color(0xFFE6E1D6)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Subtasks',
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w900,
              letterSpacing: 0.8,
              color: Color(0xFFFFC815),
            ),
          ),
          const SizedBox(height: 8),
          ...subtasks
              .take(4)
              .map(
                (s) => Padding(
                  padding: const EdgeInsets.only(bottom: 6),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        '•',
                        style: TextStyle(
                          fontSize: 14,
                          color: Color(0xFFFFC815),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          s['title']?.toString() ?? 'Untitled subtask',
                          style: const TextStyle(
                            fontSize: 13.2,
                            height: 1.45,
                            fontWeight: FontWeight.w600,
                            color: Color(0xFF4B444D),
                          ),
                        ),
                      ),
                    ],
                  ),
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
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: tooltip,
      child: Material(
        color: Colors.white.withValues(alpha: 0.78),
        shape: const CircleBorder(),
        child: InkWell(
          customBorder: const CircleBorder(),
          onTap: onTap,
          child: Container(
            width: 50,
            height: 50,
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
