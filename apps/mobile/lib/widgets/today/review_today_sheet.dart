import 'package:flutter/material.dart';

class ReviewTodaySheet extends StatelessWidget {
  const ReviewTodaySheet({
    super.key,
    required this.payload,
    required this.openTasks,
    required this.onDefer,
    required this.onGoLive,
  });

  final Map<String, dynamic> payload;
  final List<Map<String, dynamic>> openTasks;
  final VoidCallback onDefer;
  final VoidCallback onGoLive;

  @override
  Widget build(BuildContext context) {
    final summary = payload['summary'] as Map<String, dynamic>?;
    final done = summary?['done'] as int? ?? 0;
    final total = summary?['total'] as int? ?? 0;
    final prompt = payload['prompt'] as String? ?? '';
    return Padding(
      padding: EdgeInsets.only(
        bottom: MediaQuery.of(context).viewInsets.bottom,
      ),
      child: DraggableScrollableSheet(
        expand: false,
        initialChildSize: 0.55,
        minChildSize: 0.35,
        maxChildSize: 0.9,
        builder: (context, scrollController) {
          return ListView(
            controller: scrollController,
            padding: const EdgeInsets.all(24),
            children: [
              Text(
                'Review your day',
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: 8),
              Text(
                payload['greeting'] as String? ?? '',
                style: TextStyle(color: Colors.white.withValues(alpha: 0.7)),
              ),
              const SizedBox(height: 16),
              Text(
                '$done of $total tasks done',
                style: Theme.of(context).textTheme.titleMedium,
              ),
              const SizedBox(height: 8),
              Text(prompt),
              if (openTasks.isNotEmpty) ...[
                const SizedBox(height: 16),
                Text(
                  'Still open',
                  style: TextStyle(color: Colors.white.withValues(alpha: 0.55)),
                ),
                ...openTasks.map(
                  (t) => ListTile(
                    dense: true,
                    contentPadding: EdgeInsets.zero,
                    title: Text(t['title'] as String),
                  ),
                ),
              ],
              const SizedBox(height: 24),
              FilledButton(
                onPressed: onDefer,
                child: const Text('Carry to tomorrow'),
              ),
              const SizedBox(height: 8),
              OutlinedButton(
                onPressed: onGoLive,
                child: const Text('Go Live with AiPal'),
              ),
            ],
          );
        },
      ),
    );
  }
}
