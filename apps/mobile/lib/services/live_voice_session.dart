import 'dart:async';
import 'dart:convert';
import 'dart:developer' as developer;
import 'dart:typed_data';

import 'package:uuid/uuid.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../config.dart';
import 'audio_playback_queue.dart';
import 'pcm_stream_recorder.dart';

typedef LiveVoiceMessageHandler = void Function(Map<String, dynamic> msg);

enum VoiceRuntimeState {
  idle,
  listening,
  userSpeaking,
  thinking,
  speaking,
  interrupted,
  cancelled,
  reconnecting,
  failed,
}

/// Full-duplex Live Voice v2 session over WebSocket.
class LiveVoiceSession {
  LiveVoiceSession({
    required this.onMessage,
    this.onSpeechStart,
    this.isSpeakingForVad,
    this.bargeInThresholdDb = -34.0,
    this.immediateBargeInThresholdDb = -24.0,
  });

  final LiveVoiceMessageHandler onMessage;
  final void Function()? onSpeechStart;
  final bool Function()? isSpeakingForVad;
  final double bargeInThresholdDb;
  final double immediateBargeInThresholdDb;

  static const _tickMs = 80;
  static const _voiceProtocol = '4.0';
  static const _sampleRate = 16000;
  static const _channels = 1;
  static const _uuid = Uuid();

  WebSocketChannel? _channel;
  StreamSubscription<dynamic>? _socketSub;
  Completer<void>? _readyCompleter;
  final PcmStreamRecorder _recorder = PcmStreamRecorder();
  AudioPlaybackQueue? _playback;
  Timer? _vadTicker;
  String? sessionId;
  String? _currentTurnId;
  String? _serverTurnId;
  bool _active = false;
  bool _inSegment = false;
  bool _speaking = false;
  bool _vadTickRunning = false;
  bool _bargeInSent = false;
  int _bargeInAccumMs = 0;
  int _audioSequence = 0;
  final Set<String> _playedChunks = <String>{};
  final Set<String> _cancelledPlaybackTurns = <String>{};
  String? _activePlaybackTurnId;
  VoiceRuntimeState _runtimeState = VoiceRuntimeState.idle;

  bool get isActive => _active;
  bool get isSpeaking => _speaking;
  bool get isPlaybackActive => _playback?.isPlaying ?? false;

  void _setState(VoiceRuntimeState next, {String? turnId}) {
    if (_runtimeState == next) return;
    developer.log(
      'voice_state ${_runtimeState.name}->${next.name} turn=${turnId ?? _currentTurnId ?? _serverTurnId ?? "-"}',
      name: 'aipal.voice',
    );
    _runtimeState = next;
  }

  Future<bool> ensureMicPermission() async {
    return _recorder.ensureMicPermission();
  }

  Future<void> start(String token) async {
    await stop();
    _playback = AudioPlaybackQueue(
      onIdle: () {
        final completedTurn = _activePlaybackTurnId ?? _serverTurnId;
        if (completedTurn != null) {
          _channel?.sink.add(
            jsonEncode({'type': 'playback_complete', 'turn_id': completedTurn}),
          );
        }
        _speaking = false;
        _activePlaybackTurnId = null;
        _serverTurnId = null;
      },
    );
    _channel = WebSocketChannel.connect(Uri.parse(AppConfig.wsUrl(token)));
    _active = true;
    _setState(VoiceRuntimeState.reconnecting);
    _readyCompleter = Completer<void>();

    _socketSub = _channel!.stream.listen(
      _onWsMessage,
      onError: _onSocketError,
      onDone: _onSocketDone,
      cancelOnError: true,
    );

    await _readyCompleter!.future.timeout(const Duration(seconds: 30));

    _recorder.onPcm = _onPcmFrame;
    await _recorder.start();
    _setState(VoiceRuntimeState.listening);

    _vadTicker = Timer.periodic(const Duration(milliseconds: _tickMs), (_) {
      unawaited(_vadTick());
    });
  }

  Future<void> stop() async {
    _active = false;
    _vadTicker?.cancel();
    _vadTicker = null;
    try {
      _channel?.sink.add(jsonEncode({'type': 'end'}));
    } catch (_) {}
    await _channel?.sink.close();
    await _socketSub?.cancel();
    _socketSub = null;
    _channel = null;
    _readyCompleter = null;
    await _recorder.stop();
    await _playback?.dispose();
    _playback = null;
    sessionId = null;
    _currentTurnId = null;
    _serverTurnId = null;
    _inSegment = false;
    _speaking = false;
    _bargeInAccumMs = 0;
    _bargeInSent = false;
    _audioSequence = 0;
    _playedChunks.clear();
    _cancelledPlaybackTurns.clear();
    _activePlaybackTurnId = null;
    _setState(VoiceRuntimeState.idle);
  }

  Future<void> dispose() async {
    await stop();
    await _recorder.dispose();
    _recorder.onPcm = null;
  }

  void sendInterrupt() {
    final turnId = _serverTurnId ?? _activePlaybackTurnId;
    if (turnId != null) {
      _cancelledPlaybackTurns.add(turnId);
      _channel?.sink.add(jsonEncode({'type': 'interrupt', 'turn_id': turnId}));
    } else {
      _channel?.sink.add(jsonEncode({'type': 'interrupt', 'turn_id': 'all'}));
    }
    unawaited(_playback?.flush());
    _speaking = false;
    _currentTurnId = null;
    _serverTurnId = null;
    _bargeInAccumMs = 0;
    _playedChunks.clear();
    _activePlaybackTurnId = null;
    _setState(VoiceRuntimeState.interrupted, turnId: _currentTurnId);
  }

  void sendTextTurn(String text) {
    final turnId = _uuid.v4();
    _currentTurnId = turnId;
    _channel?.sink.add(
      jsonEncode({'type': 'text_turn', 'text': text, 'turn_id': turnId}),
    );
  }

  /// Play proactive greeting TTS without sending through the LLM turn pipeline.
  Future<void> playGreeting(Uint8List bytes, String mime) async {
    if (!_active || _playback == null || bytes.isEmpty) return;
    if (_playback!.isPlaying || _speaking) return;
    _activePlaybackTurnId = 'greeting';
    _speaking = true;
    _setState(VoiceRuntimeState.speaking, turnId: 'greeting');
    await _playback!.enqueue(bytes: bytes, mime: mime);
  }

  void _onPcmFrame(Uint8List bytes) {
    if (!_active || _channel == null) return;
    _sendAudioFrame(bytes);
  }

  void _sendAudioFrame(Uint8List bytes) {
    if (!_active || _channel == null || bytes.isEmpty) return;
    _channel!.sink.add(
      jsonEncode({
        'type': 'audio_frame',
        'voice_protocol': _voiceProtocol,
        'turn_id': 'stream',
        'sequence': _audioSequence++,
        'encoding': 'pcm_s16le',
        'sample_rate': _sampleRate,
        'channels': _channels,
        'data': base64Encode(bytes),
      }),
    );
  }

  void _onWsMessage(dynamic data) {
    final msg = jsonDecode(data as String) as Map<String, dynamic>;
    final type = msg['type'] as String?;
    if (type == 'session_started') {
      final protocol = msg['voice_protocol']?.toString();
      if (protocol != _voiceProtocol) {
        final error = StateError(
          'Unsupported voice protocol ${protocol ?? "missing"}; expected $_voiceProtocol',
        );
        if (!(_readyCompleter?.isCompleted ?? true)) {
          _readyCompleter!.completeError(error);
        }
        unawaited(stop());
        return;
      }
      sessionId = msg['session_id'] as String?;
      if (!(_readyCompleter?.isCompleted ?? true)) {
        _readyCompleter!.complete();
      }
    }
    if (type == 'state') {
      final s = msg['state'] as String?;
      _speaking = s == 'speaking';
      if (s == 'thinking') _setState(VoiceRuntimeState.thinking);
      if (s == 'speaking') _setState(VoiceRuntimeState.speaking);
      if (s == 'listening') {
        _setState(
          _inSegment
              ? VoiceRuntimeState.userSpeaking
              : VoiceRuntimeState.listening,
          turnId: _currentTurnId,
        );
      }
    }
    if (type == 'speech_detected') {
      _currentTurnId = msg['turn_id']?.toString();
      _inSegment = true;
      _bargeInSent = false;
      _setState(VoiceRuntimeState.userSpeaking, turnId: _currentTurnId);
      onSpeechStart?.call();
    }
    if (type == 'thinking_pause' || type == 'speech_resumed') {
      _setState(VoiceRuntimeState.userSpeaking, turnId: _currentTurnId);
    }
    if (type == 'endpoint_detected') {
      _inSegment = false;
      _bargeInSent = false;
      _setState(VoiceRuntimeState.thinking, turnId: _currentTurnId);
      _currentTurnId = null;
    }
    if (type == 'tts_chunk') {
      _bargeInSent = false;
      _serverTurnId = msg['turn_id'] as String? ?? _serverTurnId;
      final turnId = msg['turn_id']?.toString() ?? '';
      if (_cancelledPlaybackTurns.contains(turnId)) {
        onMessage(msg);
        return;
      }
      final chunkIndex = msg['chunk_index'] is int
          ? msg['chunk_index'] as int
          : int.tryParse(msg['chunk_index']?.toString() ?? '');
      final chunkKey = chunkIndex == null ? null : '$turnId:$chunkIndex';
      if (chunkKey != null && !_playedChunks.add(chunkKey)) {
        onMessage(msg);
        return;
      }
      final b64 = msg['data'] as String?;
      final mime = msg['mime'] as String? ?? 'audio/mpeg';
      if (b64 != null && b64.isNotEmpty) {
        unawaited(
          _enqueueTurnAudio(
            turnId: turnId,
            bytes: base64Decode(b64),
            mime: mime,
            chunkIndex: chunkIndex,
          ),
        );
        _speaking = true;
        _setState(VoiceRuntimeState.speaking, turnId: turnId);
      }
    }
    if (type == 'tts_complete') {
      if (!(_playback?.isPlaying ?? false)) {
        _speaking = false;
      }
    }
    if (type == 'turn_cancelled') {
      final cancelledTurnId = msg['turn_id']?.toString();
      if (cancelledTurnId != null && cancelledTurnId != 'all') {
        _cancelledPlaybackTurns.add(cancelledTurnId);
      } else if (_serverTurnId != null) {
        _cancelledPlaybackTurns.add(_serverTurnId!);
      }
      unawaited(_playback?.flush());
      _speaking = false;
      _serverTurnId = null;
      _bargeInAccumMs = 0;
      _playedChunks.clear();
      _activePlaybackTurnId = null;
      if (!_inSegment) {
        _currentTurnId = null;
        _setState(VoiceRuntimeState.cancelled);
      } else {
        _setState(VoiceRuntimeState.userSpeaking, turnId: _currentTurnId);
      }
    }
    if (type == 'turn_complete') {
      if (!(_playback?.isPlaying ?? false)) {
        _speaking = false;
      }
      if (!_inSegment) {
        _currentTurnId = null;
      }
      if (!(_playback?.isPlaying ?? false)) {
        _serverTurnId = null;
      }
      if (!_inSegment && !(_playback?.isPlaying ?? false)) {
        _setState(VoiceRuntimeState.listening);
      }
    }
    onMessage(msg);
  }

  void _onSocketError(Object error, [StackTrace? stackTrace]) {
    _failSocket('Live voice connection failed: $error');
  }

  void _onSocketDone() {
    if (_active) {
      _failSocket('Live voice connection closed.');
    }
  }

  void _failSocket(String message) {
    if (!(_readyCompleter?.isCompleted ?? true)) {
      _readyCompleter!.completeError(StateError(message));
    }
    _active = false;
    _vadTicker?.cancel();
    _vadTicker = null;
    unawaited(_recorder.stop());
    unawaited(_playback?.flush());
    _setState(VoiceRuntimeState.failed);
    onMessage({'type': 'state', 'state': 'failed', 'message': message});
  }

  Future<void> _enqueueTurnAudio({
    required String turnId,
    required Uint8List bytes,
    required String mime,
    int? chunkIndex,
  }) async {
    final playback = _playback;
    if (playback == null || _cancelledPlaybackTurns.contains(turnId)) return;
    if (_activePlaybackTurnId != null && _activePlaybackTurnId != turnId) {
      await playback.flush();
      _playedChunks.clear();
    }
    _activePlaybackTurnId = turnId;
    if (_cancelledPlaybackTurns.contains(turnId)) return;
    await playback.enqueue(bytes: bytes, mime: mime, chunkIndex: chunkIndex);
  }

  Future<void> _vadTick() async {
    if (!_active || _vadTickRunning) return;
    _vadTickRunning = true;
    try {
      await _runVadTick();
    } finally {
      _vadTickRunning = false;
    }
  }

  Future<void> _runVadTick() async {
    final aiSpeaking =
        _speaking ||
        (_playback?.isPlaying ?? false) ||
        (isSpeakingForVad?.call() ?? false);
    if (!aiSpeaking || _bargeInSent) {
      _bargeInAccumMs = 0;
      return;
    }
    final amp = await _recorder.getAmplitude();
    if (amp.current > immediateBargeInThresholdDb) {
      developer.log(
        'barge_in_immediate db=${amp.current.toStringAsFixed(1)}',
        name: 'aipal.voice',
      );
      _bargeInSent = true;
      sendInterrupt();
      return;
    }
    if (amp.current > bargeInThresholdDb) {
      _bargeInAccumMs += _tickMs;
    } else {
      _bargeInAccumMs = 0;
    }
    if (_bargeInAccumMs >= _tickMs * 2) {
      _bargeInSent = true;
      sendInterrupt();
    }
  }
}
