import 'package:flutter/foundation.dart';

/// Web stub — wake word not available (no always-on mic).
class WakeWordService {
  WakeWordService({required this.onWake, this.shouldSuppress});

  final VoidCallback onWake;
  final bool Function()? shouldSuppress;

  String get phrase => 'Hi Pal';
  bool get isListening => false;

  Future<bool> ensureMicPermission() async => false;

  Future<bool> init() async => false;

  Future<void> start() async {}

  Future<void> stop() async {}

  Future<void> dispose() async {}
}
