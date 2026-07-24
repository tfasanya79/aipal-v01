import 'package:flutter/material.dart';

class TodayEmpty extends StatelessWidget {
  const TodayEmpty({super.key, this.onGoCompanion});

  final VoidCallback? onGoCompanion;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        return SingleChildScrollView(
          physics: const BouncingScrollPhysics(),
          child: ConstrainedBox(
            constraints: BoxConstraints(minHeight: constraints.maxHeight),
            child: Center(
              child: Container(
                width: double.infinity,
                constraints: const BoxConstraints(maxWidth: 460),
                padding: const EdgeInsets.fromLTRB(28, 32, 28, 30),
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.62),
                  borderRadius: BorderRadius.circular(34),
                  border: Border.all(
                    color: Colors.white.withValues(alpha: 0.88),
                  ),
                  boxShadow: [
                    BoxShadow(
                      color: const Color(0xFF1A1F2C).withValues(alpha: 0.05),
                      blurRadius: 42,
                      offset: const Offset(0, 22),
                    ),
                  ],
                ),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      width: 76,
                      height: 76,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        gradient: const LinearGradient(
                          begin: Alignment.topLeft,
                          end: Alignment.bottomRight,
                          colors: [Color(0xFFFFC815), Color(0xFF003B2B)],
                        ),
                        boxShadow: [
                          BoxShadow(
                            color: const Color(
                              0xFFFFC815,
                            ).withValues(alpha: 0.18),
                            blurRadius: 26,
                            offset: const Offset(0, 12),
                          ),
                        ],
                      ),
                      child: const Icon(
                        Icons.auto_awesome_rounded,
                        color: Colors.white,
                        size: 34,
                      ),
                    ),
                    const SizedBox(height: 24),
                    const Text(
                      'Nothing planned yet',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        fontFamily: 'Manrope',
                        fontSize: 24,
                        height: 1.2,
                        fontWeight: FontWeight.w800,
                        color: Color(0xFF1B1C1A),
                      ),
                    ),
                    const SizedBox(height: 10),
                    const Text(
                      'Start with Companion and let AiPal shape your day into a calm, focused plan.',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        fontSize: 14,
                        height: 1.55,
                        fontWeight: FontWeight.w500,
                        color: Color(0xFF4B444D),
                      ),
                    ),
                    if (onGoCompanion != null) ...[
                      const SizedBox(height: 24),
                      FilledButton.icon(
                        onPressed: onGoCompanion,
                        icon: const Icon(Icons.graphic_eq_rounded),
                        label: const Text('Open Companion'),
                        style: FilledButton.styleFrom(
                          backgroundColor: const Color(0xFFFFC815),
                          foregroundColor: Colors.white,
                          minimumSize: const Size.fromHeight(54),
                          shape: const StadiumBorder(),
                          textStyle: const TextStyle(
                            fontSize: 14,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}
