import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../providers/app_state.dart';
import 'home_shell.dart';

const _ivory = Color(0xFFFAF9F5);
const _brandGreen = Color(0xFF003B2B);
const _teal = Color(0xFF003B2B);
const _ink = Color(0xFF26232A);

class CommitmentsScreen extends StatefulWidget {
  const CommitmentsScreen({super.key});

  @override
  State<CommitmentsScreen> createState() => _CommitmentsScreenState();
}

class _CommitmentsScreenState extends State<CommitmentsScreen> {
  Future<Map<String, List<dynamic>>>? _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<Map<String, List<dynamic>>> _load() async {
    final api = context.read<AppState>().api;
    final results = await Future.wait([
      api.getCommitments(),
      api.getDueCommitments(),
    ]);
    return {'commitments': results[0], 'due': results[1]};
  }

  Future<void> _refresh() async {
    if (!mounted) return;
    setState(() => _future = _load());
  }

  Future<void> _complete(String id) async {
    await context.read<AppState>().api.completeCommitment(id);
    await _refresh();
  }

  Future<void> _dismiss(String id) async {
    await context.read<AppState>().api.dismissCommitment(id);
    await _refresh();
  }

  @override
  Widget build(BuildContext context) {
    return AiPalShellScaffold(
      title: 'Commitments',
      subtitle: 'Promises and follow-ups AiPal is holding gently',
      showDesktopSidebar: false,
      showMobileBottomNav: false,
      onNotificationsTap: () {},
      onProfileTap: () {},
      body: Container(
        color: _ivory,
        child: Stack(
          children: [
            const _Atmosphere(),
            FutureBuilder<Map<String, List<dynamic>>>(
              future: _future,
              builder: (context, snapshot) {
                if (snapshot.connectionState == ConnectionState.waiting) {
                  return const Center(
                    child: CircularProgressIndicator(color: _teal),
                  );
                }
                final commitments = snapshot.data?['commitments'] ?? const [];
                final due = snapshot.data?['due'] ?? const [];
                final open = commitments
                    .where((item) => item['status'] == 'open')
                    .toList();
                final completed = commitments
                    .where((item) => item['status'] == 'completed')
                    .toList();
                final dismissed = commitments
                    .where((item) => item['status'] == 'dismissed')
                    .toList();

                return RefreshIndicator(
                  color: _teal,
                  onRefresh: _refresh,
                  child: ListView(
                    padding: const EdgeInsets.fromLTRB(20, 24, 20, 96),
                    children: [
                      _HeroPanel(
                        openCount: open.length,
                        dueCount: due.length,
                        completedCount: completed.length,
                      ),
                      const SizedBox(height: 18),
                      _CommitmentSection(
                        title: 'Due follow-ups',
                        subtitle: 'Things AiPal can check in on today',
                        items: due,
                        emptyText: 'No due follow-ups right now.',
                        highlighted: true,
                        onComplete: _complete,
                        onDismiss: _dismiss,
                      ),
                      const SizedBox(height: 16),
                      _CommitmentSection(
                        title: 'Open commitments',
                        subtitle: 'Promises and plans still active',
                        items: open,
                        emptyText: 'No open commitments yet.',
                        onComplete: _complete,
                        onDismiss: _dismiss,
                      ),
                      const SizedBox(height: 16),
                      _CommitmentSection(
                        title: 'Completed',
                        subtitle: 'Finished commitments',
                        items: completed,
                        emptyText: 'Completed commitments will appear here.',
                        compact: true,
                        onComplete: _complete,
                        onDismiss: _dismiss,
                      ),
                      const SizedBox(height: 16),
                      _CommitmentSection(
                        title: 'Dismissed',
                        subtitle: 'Commitments you chose not to track',
                        items: dismissed,
                        emptyText: 'Dismissed commitments will appear here.',
                        compact: true,
                        onComplete: _complete,
                        onDismiss: _dismiss,
                      ),
                    ],
                  ),
                );
              },
            ),
          ],
        ),
      ),
    );
  }
}

class _HeroPanel extends StatelessWidget {
  const _HeroPanel({
    required this.openCount,
    required this.dueCount,
    required this.completedCount,
  });

  final int openCount;
  final int dueCount;
  final int completedCount;

  @override
  Widget build(BuildContext context) {
    return _GlassPanel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Commitment tracking',
            style: TextStyle(
              fontSize: 28,
              fontWeight: FontWeight.w800,
              color: _ink,
            ),
          ),
          const SizedBox(height: 8),
          const Text(
            'Not tasks. Not reminders. Just the things you said you wanted AiPal to remember and follow up on.',
            style: TextStyle(color: Color(0xFF625D66), height: 1.35),
          ),
          const SizedBox(height: 18),
          Row(
            children: [
              _MetricChip(label: 'Open', value: '$openCount'),
              const SizedBox(width: 10),
              _MetricChip(label: 'Due', value: '$dueCount', accent: _teal),
              const SizedBox(width: 10),
              _MetricChip(label: 'Done', value: '$completedCount'),
            ],
          ),
        ],
      ),
    );
  }
}

class _CommitmentSection extends StatelessWidget {
  const _CommitmentSection({
    required this.title,
    required this.subtitle,
    required this.items,
    required this.emptyText,
    required this.onComplete,
    required this.onDismiss,
    this.highlighted = false,
    this.compact = false,
  });

  final String title;
  final String subtitle;
  final List<dynamic> items;
  final String emptyText;
  final bool highlighted;
  final bool compact;
  final Future<void> Function(String id) onComplete;
  final Future<void> Function(String id) onDismiss;

  @override
  Widget build(BuildContext context) {
    return _GlassPanel(
      borderColor: highlighted
          ? _teal.withValues(alpha: 0.25)
          : Colors.white.withValues(alpha: 0.68),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: const TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w800,
                        color: _brandGreen,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      subtitle,
                      style: const TextStyle(color: Color(0xFF706A73)),
                    ),
                  ],
                ),
              ),
              _CountBadge(count: items.length),
            ],
          ),
          const SizedBox(height: 14),
          if (items.isEmpty)
            Text(emptyText, style: const TextStyle(color: Color(0xFF77717A)))
          else
            ...items.map(
              (item) => Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: _CommitmentCard(
                  item: item as Map<String, dynamic>,
                  compact: compact,
                  onComplete: onComplete,
                  onDismiss: onDismiss,
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _CommitmentCard extends StatelessWidget {
  const _CommitmentCard({
    required this.item,
    required this.compact,
    required this.onComplete,
    required this.onDismiss,
  });

  final Map<String, dynamic> item;
  final bool compact;
  final Future<void> Function(String id) onComplete;
  final Future<void> Function(String id) onDismiss;

  @override
  Widget build(BuildContext context) {
    final status = item['status']?.toString() ?? 'open';
    final id = item['id']?.toString() ?? '';
    final title = item['title']?.toString() ?? 'Commitment';
    final content = item['content']?.toString() ?? '';
    final dueLabel = _formatDate(item['due_at']);
    final followUpLabel = _formatDate(item['follow_up_at']);
    final related = item['related_entity_name']?.toString();
    final confidence = item['confidence'];

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.78),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: _teal.withValues(alpha: 0.10)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Text(
                  title,
                  style: const TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w800,
                    color: _ink,
                  ),
                ),
              ),
              _StatusBadge(status: status),
            ],
          ),
          if (!compact && content.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(
              content,
              style: const TextStyle(color: Color(0xFF5F5963), height: 1.35),
            ),
          ],
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              if (dueLabel != null)
                _InfoPill(icon: Icons.event_rounded, text: dueLabel),
              if (followUpLabel != null)
                _InfoPill(icon: Icons.forum_rounded, text: followUpLabel),
              if (related != null && related.isNotEmpty)
                _InfoPill(icon: Icons.hub_rounded, text: related),
              if (confidence is num)
                _InfoPill(
                  icon: Icons.verified_rounded,
                  text: '${(confidence * 100).round()}%',
                ),
            ],
          ),
          if (status == 'open' && id.isNotEmpty) ...[
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: () => onDismiss(id),
                    icon: const Icon(Icons.close_rounded),
                    label: const Text('Dismiss'),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: _brandGreen,
                    ),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: FilledButton.icon(
                    onPressed: () => onComplete(id),
                    icon: const Icon(Icons.check_rounded),
                    label: const Text('Complete'),
                    style: FilledButton.styleFrom(backgroundColor: _teal),
                  ),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }

  static String? _formatDate(dynamic value) {
    if (value == null) return null;
    final parsed = DateTime.tryParse(value.toString());
    if (parsed == null) return null;
    return DateFormat('MMM d, h:mm a').format(parsed.toLocal());
  }
}

class _MetricChip extends StatelessWidget {
  const _MetricChip({
    required this.label,
    required this.value,
    this.accent = _brandGreen,
  });

  final String label;
  final String value;
  final Color accent;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
        decoration: BoxDecoration(
          color: accent.withValues(alpha: 0.10),
          borderRadius: BorderRadius.circular(16),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              value,
              style: TextStyle(
                fontSize: 22,
                fontWeight: FontWeight.w900,
                color: accent,
              ),
            ),
            Text(label, style: const TextStyle(color: Color(0xFF67616B))),
          ],
        ),
      ),
    );
  }
}

class _CountBadge extends StatelessWidget {
  const _CountBadge({required this.count});
  final int count;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
    decoration: BoxDecoration(
      color: _brandGreen.withValues(alpha: 0.10),
      borderRadius: BorderRadius.circular(999),
    ),
    child: Text(
      '$count',
      style: const TextStyle(color: _brandGreen, fontWeight: FontWeight.w800),
    ),
  );
}

class _StatusBadge extends StatelessWidget {
  const _StatusBadge({required this.status});
  final String status;

  @override
  Widget build(BuildContext context) {
    final color = status == 'completed'
        ? _teal
        : status == 'dismissed'
        ? const Color(0xFF827A86)
        : _brandGreen;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        status,
        style: TextStyle(color: color, fontWeight: FontWeight.w700),
      ),
    );
  }
}

class _InfoPill extends StatelessWidget {
  const _InfoPill({required this.icon, required this.text});
  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
    decoration: BoxDecoration(
      color: _ivory.withValues(alpha: 0.92),
      borderRadius: BorderRadius.circular(999),
    ),
    child: Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 15, color: _teal),
        const SizedBox(width: 6),
        Text(
          text,
          style: const TextStyle(
            fontSize: 12,
            color: _ink,
            fontWeight: FontWeight.w600,
          ),
        ),
      ],
    ),
  );
}

class _GlassPanel extends StatelessWidget {
  const _GlassPanel({required this.child, this.borderColor});

  final Widget child;
  final Color? borderColor;

  @override
  Widget build(BuildContext context) => ClipRRect(
    borderRadius: BorderRadius.circular(26),
    child: BackdropFilter(
      filter: ImageFilter.blur(sigmaX: 18, sigmaY: 18),
      child: Container(
        padding: const EdgeInsets.all(18),
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.70),
          borderRadius: BorderRadius.circular(26),
          border: Border.all(
            color: borderColor ?? Colors.white.withValues(alpha: 0.74),
          ),
          boxShadow: [
            BoxShadow(
              color: _brandGreen.withValues(alpha: 0.06),
              blurRadius: 24,
              offset: const Offset(0, 14),
            ),
          ],
        ),
        child: child,
      ),
    ),
  );
}

class _Atmosphere extends StatelessWidget {
  const _Atmosphere();

  @override
  Widget build(BuildContext context) => IgnorePointer(
    child: DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            _ivory,
            _teal.withValues(alpha: 0.08),
            _brandGreen.withValues(alpha: 0.08),
          ],
        ),
      ),
      child: const SizedBox.expand(),
    ),
  );
}
