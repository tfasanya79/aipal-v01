import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import 'task_category.dart';

class TimelineTaskTile extends StatelessWidget {
  const TimelineTaskTile({
    super.key,
    required this.task,
    this.dimmed = false,
    this.showDragHandle = false,
    this.dragIndex = 0,
    this.onTap,
    this.onComplete,
  });

  final Map<String, dynamic> task;
  final bool dimmed;
  final bool showDragHandle;
  final int dragIndex;
  final VoidCallback? onTap;
  final VoidCallback? onComplete;

  @override
  Widget build(BuildContext context) {
    final done = task['status'] == 'done';
    final color = categoryColor(task['category'] as String?);
    final est = formatEstimate(task['estimated_minutes'] as int?);
    final due = task['due_at'] as String?;
    String? timeLabel;
    if (due != null) {
      try {
        timeLabel = DateFormat.jm().format(DateTime.parse(due).toLocal());
      } catch (_) {}
    }
    final rawTitle = task['title'] as String? ?? '';
    final words = rawTitle.split(RegExp(r'\s+'));
    final displayTitle = words.length > 6
        ? '${words.take(6).join(' ')}…'
        : rawTitle;
    final opacity = dimmed || done ? 0.4 : 1.0;
    return Opacity(
      opacity: opacity,
      child: ListTile(
        onTap: onTap,
        leading: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (showDragHandle)
              ReorderableDragStartListener(
                index: dragIndex,
                child: Icon(
                  Icons.drag_handle,
                  color: Colors.white.withValues(alpha: 0.35),
                ),
              ),
            Container(
              width: 4,
              height: 36,
              decoration: BoxDecoration(
                color: color,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            const SizedBox(width: 8),
            Icon(
              categoryIcon(task['category'] as String?),
              size: 20,
              color: color,
            ),
          ],
        ),
        title: Text(
          displayTitle,
          style: TextStyle(
            decoration: done ? TextDecoration.lineThrough : null,
          ),
        ),
        subtitle: timeLabel != null || est.isNotEmpty
            ? Text(
                [
                  if (timeLabel != null) timeLabel,
                  if (est.isNotEmpty) est,
                ].join(' · '),
              )
            : null,
        trailing: done
            ? const Icon(Icons.check_circle, color: Colors.white38)
            : IconButton(
                icon: const Icon(Icons.check_circle_outline),
                onPressed: onComplete,
              ),
      ),
    );
  }
}
