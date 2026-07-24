import 'dart:async';
import 'dart:ui';

import 'package:flutter/material.dart';

class FocusTimerBar extends StatefulWidget {
  const FocusTimerBar({
    super.key,
    required this.taskTitle,
    required this.totalSeconds,
    required this.onComplete,
    required this.onCancel,
  });

  final String taskTitle;
  final int totalSeconds;
  final VoidCallback onComplete;
  final VoidCallback onCancel;

  @override
  State<FocusTimerBar> createState() => FocusTimerBarState();
}

class FocusTimerBarState extends State<FocusTimerBar> {
  late int _remaining;
  Timer? _timer;
  bool _paused = false;

  @override
  void initState() {
    super.initState();
    _remaining = widget.totalSeconds;
    _start();
  }

  void _start() {
    _timer?.cancel();
    _timer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (_paused) return;

      if (_remaining <= 1) {
        _timer?.cancel();
        widget.onComplete();
      } else {
        setState(() => _remaining--);
      }
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  String get _label {
    final m = _remaining ~/ 60;
    final s = _remaining % 60;
    return '${m.toString().padLeft(2, '0')}:${s.toString().padLeft(2, '0')}';
  }

  double get _progress {
    if (widget.totalSeconds <= 0) return 0;
    return (_remaining / widget.totalSeconds).clamp(0.0, 1.0);
  }

  @override
  Widget build(BuildContext context) {
    final completed = 1 - _progress;

    return SafeArea(
      top: false,
      bottom: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(30),
          child: BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 26, sigmaY: 26),
            child: Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: 0.72),
                borderRadius: BorderRadius.circular(30),
                border: Border.all(color: Colors.white.withValues(alpha: 0.9)),
                boxShadow: [
                  BoxShadow(
                    color: const Color(0xFF1A1F2C).withValues(alpha: 0.08),
                    blurRadius: 36,
                    offset: const Offset(0, 18),
                  ),
                ],
              ),
              child: Column(
                children: [
                  Row(
                    children: [
                      SizedBox(
                        width: 72,
                        height: 72,
                        child: Stack(
                          alignment: Alignment.center,
                          children: [
                            SizedBox(
                              width: 72,
                              height: 72,
                              child: CircularProgressIndicator(
                                value: completed,
                                strokeWidth: 6,
                                strokeCap: StrokeCap.round,
                                backgroundColor: const Color(0xFFE3E2DF),
                                color: const Color(0xFFFFC815),
                              ),
                            ),
                            Column(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                const Icon(
                                  Icons.timer_rounded,
                                  size: 15,
                                  color: Color(0xFFFFC815),
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  _label,
                                  style: const TextStyle(
                                    fontFamily: 'Manrope',
                                    fontSize: 14,
                                    fontWeight: FontWeight.w900,
                                    fontFeatures: [
                                      FontFeature.tabularFigures(),
                                    ],
                                    color: Color(0xFF1B1C1A),
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ),
                      ),

                      const SizedBox(width: 16),

                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Container(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 10,
                                vertical: 5,
                              ),
                              decoration: BoxDecoration(
                                color: _paused
                                    ? const Color(0xFFF4F4F0)
                                    : const Color(0xFFFFF2B8),
                                borderRadius: BorderRadius.circular(999),
                              ),
                              child: Text(
                                _paused ? 'PAUSED' : 'FOCUS MODE',
                                style: TextStyle(
                                  fontSize: 10.5,
                                  fontWeight: FontWeight.w900,
                                  letterSpacing: 1.1,
                                  color: _paused
                                      ? const Color(0xFF575C6B)
                                      : const Color(0xFFFFC815),
                                ),
                              ),
                            ),
                            const SizedBox(height: 9),
                            Text(
                              widget.taskTitle,
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                fontFamily: 'Manrope',
                                fontSize: 17,
                                height: 1.25,
                                fontWeight: FontWeight.w800,
                                color: Color(0xFF1B1C1A),
                              ),
                            ),
                            const SizedBox(height: 8),
                            Text(
                              '${(completed * 100).round()}% complete',
                              style: const TextStyle(
                                fontSize: 12.5,
                                fontWeight: FontWeight.w600,
                                color: Color(0xFF4B444D),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),

                  const SizedBox(height: 14),

                  ClipRRect(
                    borderRadius: BorderRadius.circular(999),
                    child: LinearProgressIndicator(
                      value: completed,
                      minHeight: 6,
                      backgroundColor: const Color(0xFFE3E2DF),
                      valueColor: const AlwaysStoppedAnimation<Color>(
                        Color(0xFFFFC815),
                      ),
                    ),
                  ),

                  const SizedBox(height: 14),

                  Row(
                    children: [
                      Expanded(
                        child: _FocusActionButton(
                          icon: _paused
                              ? Icons.play_arrow_rounded
                              : Icons.pause_rounded,
                          label: _paused ? 'Resume' : 'Pause',
                          filled: true,
                          onTap: () => setState(() => _paused = !_paused),
                        ),
                      ),
                      const SizedBox(width: 8),
                      _FocusIconButton(
                        icon: Icons.add_rounded,
                        tooltip: '+5 min',
                        onTap: () => setState(() => _remaining += 300),
                      ),
                      const SizedBox(width: 8),
                      _FocusIconButton(
                        icon: Icons.check_rounded,
                        tooltip: 'Complete',
                        onTap: widget.onComplete,
                      ),
                      const SizedBox(width: 8),
                      _FocusIconButton(
                        icon: Icons.close_rounded,
                        tooltip: 'Cancel',
                        onTap: widget.onCancel,
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _FocusActionButton extends StatelessWidget {
  const _FocusActionButton({
    required this.icon,
    required this.label,
    required this.onTap,
    this.filled = false,
  });

  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final bool filled;

  @override
  Widget build(BuildContext context) {
    return FilledButton.icon(
      onPressed: onTap,
      icon: Icon(icon, size: 19),
      label: Text(label),
      style: FilledButton.styleFrom(
        backgroundColor: filled
            ? const Color(0xFFFFC815)
            : const Color(0xFFF4F4F0),
        foregroundColor: filled ? Colors.white : const Color(0xFF1B1C1A),
        minimumSize: const Size.fromHeight(48),
        shape: const StadiumBorder(),
        textStyle: const TextStyle(fontSize: 13.5, fontWeight: FontWeight.w800),
      ),
    );
  }
}

class _FocusIconButton extends StatelessWidget {
  const _FocusIconButton({
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
        color: const Color(0xFFF8F7F3),
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
