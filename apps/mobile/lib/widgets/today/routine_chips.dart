import 'package:flutter/material.dart';

class RoutineChips extends StatelessWidget {
  const RoutineChips({super.key, required this.onSelect, this.busy = false});

  final void Function(String template) onSelect;
  final bool busy;

  static const _routines = [
    (template: 'plan_day', label: 'Plan day', icon: Icons.auto_awesome_rounded),
    (template: 'deep_work', label: 'Deep work', icon: Icons.psychology_rounded),
    (template: 'break', label: 'Break', icon: Icons.spa_rounded),
    (template: 'errands', label: 'Errands', icon: Icons.checklist_rounded),
  ];

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      padding: const EdgeInsets.fromLTRB(18, 18, 18, 16),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.58),
        borderRadius: BorderRadius.circular(28),
        border: Border.all(color: Colors.white.withValues(alpha: 0.84)),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF1A1F2C).withValues(alpha: 0.04),
            blurRadius: 34,
            offset: const Offset(0, 18),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Suggest routines',
            style: TextStyle(
              fontFamily: 'Manrope',
              fontSize: 18,
              height: 1.2,
              fontWeight: FontWeight.w800,
              color: Color(0xFF1B1C1A),
            ),
          ),
          const SizedBox(height: 6),
          const Text(
            'Let AiPal shape your day with a focused starting point.',
            style: TextStyle(
              fontSize: 13,
              height: 1.45,
              fontWeight: FontWeight.w500,
              color: Color(0xFF4B444D),
            ),
          ),
          const SizedBox(height: 16),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: [
              for (final r in _routines)
                _RoutinePill(
                  label: r.label,
                  icon: r.icon,
                  busy: busy,
                  onTap: () => onSelect(r.template),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

class _RoutinePill extends StatelessWidget {
  const _RoutinePill({
    required this.label,
    required this.icon,
    required this.busy,
    required this.onTap,
  });

  final String label;
  final IconData icon;
  final bool busy;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: const Color(0xFFF8F7F3),
      borderRadius: BorderRadius.circular(999),
      child: InkWell(
        onTap: busy ? null : onTap,
        borderRadius: BorderRadius.circular(999),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(999),
            border: Border.all(color: const Color(0xFFE3E2DF)),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icon, size: 17, color: const Color(0xFFFFC815)),
              const SizedBox(width: 7),
              Text(
                label,
                style: const TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w800,
                  color: Color(0xFF1B1C1A),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
