import 'package:flutter/material.dart';

/// Small static orb mark for headers and onboarding.
class AiPalOrbMark extends StatelessWidget {
  const AiPalOrbMark({super.key, this.size = 24});

  final double size;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: const BoxDecoration(
        shape: BoxShape.circle,
        gradient: RadialGradient(
          colors: [Color(0xFFFFE0A8), Color(0xFFE8A838), Color(0xFFFFC815)],
          stops: [0.2, 0.55, 1.0],
        ),
      ),
    );
  }
}

/// Wordmark with canonical AiPal casing (A-i-P-a-l).
class AiPalLogo extends StatelessWidget {
  const AiPalLogo({super.key, this.size = 28});

  final double size;

  @override
  Widget build(BuildContext context) {
    final gold = Theme.of(context).colorScheme.primary;
    TextStyle base(double s, FontWeight w) =>
        TextStyle(fontSize: s, fontWeight: w, color: gold, height: 1.1);
    return RichText(
      text: TextSpan(
        children: [
          TextSpan(text: 'A', style: base(size, FontWeight.w800)),
          TextSpan(text: 'i', style: base(size * 0.92, FontWeight.w600)),
          TextSpan(text: 'P', style: base(size, FontWeight.w800)),
          TextSpan(text: 'al', style: base(size * 0.92, FontWeight.w600)),
        ],
      ),
    );
  }
}

/// Orb + wordmark row for app headers.
class AiPalBrandRow extends StatelessWidget {
  const AiPalBrandRow({super.key, this.logoSize = 22, this.orbSize = 22});

  final double logoSize;
  final double orbSize;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        AiPalOrbMark(size: orbSize),
        const SizedBox(width: 8),
        AiPalLogo(size: logoSize),
      ],
    );
  }
}
