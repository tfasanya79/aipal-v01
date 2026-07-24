import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../aipal_logo.dart';

class TodayHeader extends StatelessWidget {
  const TodayHeader({
    super.key,
    required this.done,
    required this.total,
    this.streakDays = 0,
    this.onReview,
  });

  final int done;
  final int total;
  final int streakDays;
  final VoidCallback? onReview;

  @override
  Widget build(BuildContext context) {
    final dateLabel = DateFormat('EEEE, MMM d').format(DateTime.now());
    final progress = total > 0 ? done / total : 0.0;
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 8, 8),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const AiPalBrandRow(logoSize: 18, orbSize: 18),
                const SizedBox(height: 6),
                Text('Today', style: Theme.of(context).textTheme.titleLarge),
                Text(
                  dateLabel,
                  style: const TextStyle(
                    color: Color(0xFF6D6655),
                    fontSize: 13,
                  ),
                ),
                if (streakDays > 0)
                  Text(
                    '$streakDays day streak',
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.primary,
                      fontSize: 12,
                    ),
                  ),
              ],
            ),
          ),
          SizedBox(
            width: 52,
            height: 52,
            child: Stack(
              alignment: Alignment.center,
              children: [
                CircularProgressIndicator(
                  value: progress,
                  strokeWidth: 4,
                  backgroundColor: const Color(0xFFFFF2B8),
                  color: Theme.of(context).colorScheme.primary,
                ),
                Text(
                  '$done/$total',
                  style: const TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
          if (onReview != null)
            IconButton(
              tooltip: 'Review your day',
              onPressed: onReview,
              icon: const Icon(Icons.nightlight_round),
            ),
        ],
      ),
    );
  }
}
