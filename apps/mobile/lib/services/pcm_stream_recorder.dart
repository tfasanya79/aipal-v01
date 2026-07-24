import 'dart:async';
import 'dart:typed_data';

import 'package:permission_handler/permission_handler.dart';
import 'package:record/record.dart';

/// Continuous 16 kHz mono PCM stream for Live Voice v2.
class PcmStreamRecorder {
  PcmStreamRecorder({this.onPcm});

  void Function(Uint8List bytes)? onPcm;

  final AudioRecorder _recorder = AudioRecorder();
  StreamSubscription<Uint8List>? _sub;
  bool _active = false;
  final BytesBuilder _frameBuffer = BytesBuilder(copy: false);
  static const int _targetFrameBytes =
      16000 * 2 * 40 ~/ 1000; // 40 ms, 16 kHz, mono PCM16.

  bool get isActive => _active;

  Future<bool> ensureMicPermission() async {
    final status = await Permission.microphone.request();
    return status.isGranted;
  }

  Future<void> start() async {
    if (_active) return;
    if (!await ensureMicPermission()) {
      throw StateError('Microphone permission denied');
    }
    final stream = await _recorder.startStream(
      const RecordConfig(
        encoder: AudioEncoder.pcm16bits,
        sampleRate: 16000,
        numChannels: 1,
        autoGain: true,
        echoCancel: true,
        noiseSuppress: true,
      ),
    );
    _sub = stream.listen(_emitSteadyFrames);
    _active = true;
  }

  void _emitSteadyFrames(Uint8List bytes) {
    final callback = onPcm;
    if (callback == null || bytes.isEmpty) return;
    _frameBuffer.add(bytes);
    var buffered = _frameBuffer.toBytes();
    var offset = 0;
    while (buffered.length - offset >= _targetFrameBytes) {
      callback(
        Uint8List.fromList(
          buffered.sublist(offset, offset + _targetFrameBytes),
        ),
      );
      offset += _targetFrameBytes;
    }
    _frameBuffer.clear();
    if (offset < buffered.length) {
      _frameBuffer.add(buffered.sublist(offset));
    }
  }

  Future<void> stop() async {
    _active = false;
    await _sub?.cancel();
    _sub = null;
    final callback = onPcm;
    if (callback != null && _frameBuffer.length > 0) {
      callback(_frameBuffer.toBytes());
    }
    _frameBuffer.clear();
    if (await _recorder.isRecording()) {
      await _recorder.stop();
    }
  }

  Future<void> dispose() async {
    await stop();
    await _recorder.dispose();
  }

  Future<Amplitude> getAmplitude() => _recorder.getAmplitude();
}
