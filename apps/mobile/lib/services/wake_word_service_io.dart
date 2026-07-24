import 'package:flutter/foundation.dart';

import 'wake_word_engine.dart';

/// Foreground OpenWakeWord listener for "Hi Pal" (iOS native; Android uses background FGS).
class WakeWordService {
  WakeWordService({required this.onWake, this.shouldSuppress});

  final VoidCallback onWake;
  final bool Function()? shouldSuppress;

  WakeWordEngine? _engine;

  bool get isListening => _engine?.isListening ?? false;
  String get phrase => WakeWordEngine.wakePhrase;

  Future<bool> ensureMicPermission() async {
    _engine ??= WakeWordEngine(onWake: onWake, shouldSuppress: shouldSuppress);
    return _engine!.ensureMicPermission();
  }

  Future<bool> init() async {
    _engine ??= WakeWordEngine(onWake: onWake, shouldSuppress: shouldSuppress);
    return _engine!.init();
  }

  Future<void> start() async {
    _engine ??= WakeWordEngine(onWake: onWake, shouldSuppress: shouldSuppress);
    await _engine!.start();
  }

  Future<void> stop() async {
    await _engine?.stop();
  }

  Future<void> dispose() async {
    await _engine?.dispose();
    _engine = null;
  }
}
