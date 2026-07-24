import 'package:flutter/material.dart';

Color categoryColor(String? category) {
  switch (category) {
    case 'work':
      return const Color(0xFF7EB8DA);
    case 'health':
      return const Color(0xFF00A36C);
    case 'home':
      return const Color(0xFFE8A838);
    case 'personal':
      return const Color(0xFFFFC815);
    default:
      return const Color(0xFFE8A838);
  }
}

IconData categoryIcon(String? category) {
  switch (category) {
    case 'work':
      return Icons.work_outline;
    case 'health':
      return Icons.favorite_outline;
    case 'home':
      return Icons.home_outlined;
    case 'personal':
      return Icons.person_outline;
    default:
      return Icons.circle_outlined;
  }
}

String formatEstimate(int? minutes) {
  if (minutes == null || minutes <= 0) return '';
  if (minutes < 60) return '${minutes}m';
  final h = minutes ~/ 60;
  final m = minutes % 60;
  return m > 0 ? '${h}h ${m}m' : '${h}h';
}
