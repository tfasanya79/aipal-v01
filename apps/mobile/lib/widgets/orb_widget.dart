import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../services/live_session.dart';

class OrbWidget extends StatefulWidget {
  const OrbWidget({super.key, required this.state, this.onTap});

  final LiveState state;
  final VoidCallback? onTap;

  @override
  State<OrbWidget> createState() => _OrbWidgetState();
}

class _OrbWidgetState extends State<OrbWidget>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 3),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Color get _coreColor {
    switch (widget.state) {
      case LiveState.resting:
        return const Color(0xFFFFC815);
      case LiveState.listening:
        return const Color(0xFF003B2B);
      case LiveState.thinking:
        return const Color(0xFF7EB8DA);
      case LiveState.speaking:
        return const Color(0xFFFFC815);
      case LiveState.reconnecting:
        return const Color(0xFFE8A838);
      case LiveState.failed:
        return const Color(0xFFD65A4A);
    }
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: widget.onTap,
      child: AnimatedBuilder(
        animation: _controller,
        builder: (context, child) {
          final pulse = 1.0 + 0.06 * math.sin(_controller.value * 2 * math.pi);
          return Container(
            width: 180 * pulse,
            height: 180 * pulse,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: RadialGradient(
                colors: [
                  _coreColor.withValues(alpha: 0.95),
                  _coreColor.withValues(alpha: 0.35),
                  Colors.transparent,
                ],
                stops: const [0.2, 0.6, 1.0],
              ),
              boxShadow: [
                BoxShadow(
                  color: _coreColor.withValues(alpha: 0.45),
                  blurRadius: 40,
                  spreadRadius: 8,
                ),
              ],
            ),
            child: Center(
              child: Text(
                widget.state == LiveState.resting ? 'Tap to go Live' : 'AiPal',
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.9),
                  fontWeight: FontWeight.w600,
                  fontSize: 14,
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}
