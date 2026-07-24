import 'package:flutter/foundation.dart'
    show TargetPlatform, defaultTargetPlatform, kIsWeb;

class AppConfig {
  static const _rawApiBase = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: '',
  );
  static final String apiBase = _normalizeApiBase(
    _rawApiBase.isEmpty ? _defaultApiBase : _rawApiBase,
  );

  /// Live Voice v2: full-duplex WebSocket + PCM streaming (native).
  static const liveVoiceV2 = bool.fromEnvironment(
    'LIVE_VOICE_V2',
    defaultValue: true,
  );

  /// Production hides raw STT by default. Enable only for QA/debug builds.
  static const showLiveTranscript = bool.fromEnvironment(
    'SHOW_LIVE_TRANSCRIPT',
    defaultValue: false,
  );

  static String wsUrl(String token) {
    final base = apiBase
        .replaceFirst('https://', 'wss://')
        .replaceFirst('http://', 'ws://');
    return '$base/ws/session?token=$token';
  }

  static String _normalizeApiBase(String value) {
    var normalized = value.trim();
    if (normalized.endsWith('/')) {
      normalized = normalized.substring(0, normalized.length - 1);
    }
    final uri = Uri.tryParse(normalized);
    if (uri != null && uri.scheme == 'https' && _isLocalhost(uri.host)) {
      normalized = uri.replace(scheme: 'http').toString();
    }
    normalized = normalized.replaceFirst('/pi/v2', '/api/v2');
    if (!normalized.endsWith('/api/v2')) {
      normalized = '$normalized/api/v2';
    }
    return normalized;
  }

  static bool _isLocalhost(String host) {
    return host == 'localhost' ||
        host == '127.0.0.1' ||
        host == '0.0.0.0' ||
        host == '::1';
  }

  static String get _defaultApiBase {
    if (!kIsWeb && defaultTargetPlatform == TargetPlatform.android) {
      return 'http://10.0.2.2:8102/api/v2';
    }
    return 'http://127.0.0.1:8102/api/v2';
  }
}
