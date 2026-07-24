import 'package:flutter/material.dart';

import 'timeline_task_tile.dart';

class PriorityLanes extends StatelessWidget {
  const PriorityLanes({
    super.key,
    required this.tasks,
    required this.onComplete,
    required this.onReorderLane,
  });

  final List<Map<String, dynamic>> tasks;
  final void Function(int id) onComplete;
  final void Function(int priority, int oldIndex, int newIndex) onReorderLane;

  static const _lanes = [
    (priority: 2, label: 'High', color: Color(0xFFE8A838)),
    (priority: 1, label: 'Medium', color: Color(0xFFFFC815)),
    (priority: 0, label: 'Low', color: Color(0xFF6E7681)),
  ];

  Map<int, List<Map<String, dynamic>>> _grouped() {
    final grouped = <int, List<Map<String, dynamic>>>{};
    for (final t in tasks) {
      final p = (t['priority'] as int?) ?? 1;
      grouped.putIfAbsent(p, () => []).add(t);
    }
    return grouped;
  }

  @override
  Widget build(BuildContext context) {
    final grouped = _grouped();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (final lane in _lanes)
          if ((grouped[lane.priority] ?? []).isNotEmpty) ...[
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
              child: Row(
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 10,
                      vertical: 4,
                    ),
                    decoration: BoxDecoration(
                      color: lane.color.withValues(alpha: 0.18),
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(
                        color: lane.color.withValues(alpha: 0.45),
                      ),
                    ),
                    child: Text(
                      lane.label,
                      style: TextStyle(
                        color: lane.color,
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ],
              ),
            ),
            ReorderableListView.builder(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              buildDefaultDragHandles: false,
              itemCount: grouped[lane.priority]!.length,
              onReorderItem: (oldIndex, newIndex) =>
                  onReorderLane(lane.priority, oldIndex, newIndex),
              itemBuilder: (context, index) {
                final t = grouped[lane.priority]![index];
                return TimelineTaskTile(
                  key: ValueKey(t['id']),
                  task: t,
                  showDragHandle: true,
                  dragIndex: index,
                  onComplete: () => onComplete(t['id'] as int),
                );
              },
            ),
          ],
      ],
    );
  }
}
