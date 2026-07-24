import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

class PlanDraftCard extends StatelessWidget {
  const PlanDraftCard({
    super.key,
    required this.draft,
    required this.onConfirm,
    required this.onDiscard,
  });

  final Map<String, dynamic> draft;
  final VoidCallback onConfirm;
  final VoidCallback onDiscard;

  String _formatDue(String? iso) {
    if (iso == null || iso.isEmpty) return '';
    try {
      return DateFormat.jm().format(DateTime.parse(iso).toLocal());
    } catch (_) {
      return '';
    }
  }

  @override
  Widget build(BuildContext context) {
    final tasks =
        (draft['proposed_tasks'] as List?)?.cast<Map<String, dynamic>>() ?? [];
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      color: Theme.of(context).colorScheme.primary.withValues(alpha: 0.12),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Add to Today?',
              style: Theme.of(context).textTheme.titleSmall,
            ),
            const SizedBox(height: 8),
            ...tasks.map((t) {
              final time = _formatDue(t['due_at'] as String?);
              return Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Text(
                  time.isNotEmpty
                      ? '• ${t['title']} at $time'
                      : '• ${t['title']}',
                  style: const TextStyle(fontSize: 14),
                ),
              );
            }),
            const SizedBox(height: 10),
            Row(
              children: [
                FilledButton(
                  onPressed: onConfirm,
                  child: const Text('Confirm'),
                ),
                const SizedBox(width: 8),
                TextButton(onPressed: onDiscard, child: const Text('Not now')),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
