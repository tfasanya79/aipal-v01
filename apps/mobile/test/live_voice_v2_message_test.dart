import 'package:aipal/providers/app_state.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

void _mockAudioPlayerChannels() {
  for (final name in ['xyz.luan/audioplayers.global', 'xyz.luan/audioplayers']) {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(MethodChannel(name), (_) async => null);
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  _mockAudioPlayerChannels();

  group('Live Voice v2 message handling', () {
    test('thinking state clears lastReply before deltas', () async {
      final state = AppState();
      await Future<void>.delayed(Duration.zero);
      state.lastReply = 'stale greeting';

      state.handleLiveV2MessageForTest({'type': 'state', 'state': 'thinking'});
      expect(state.lastReply, isNull);

      state.handleLiveV2MessageForTest({'type': 'reply_delta', 'text': 'Hello'});
      expect(state.lastReply, 'Hello');

      state.handleLiveV2MessageForTest({
        'type': 'turn_complete',
        'reply': 'Hello there.',
      });
      expect(state.lastReply, 'Hello there.');
    });

    test('reply_delta does not accumulate stale text across turns', () async {
      final state = AppState();
      await Future<void>.delayed(Duration.zero);
      state.lastReply = 'old turn reply';

      state.handleLiveV2MessageForTest({'type': 'transcript_final', 'text': 'new question'});
      expect(state.lastReply, isNull);

      state.handleLiveV2MessageForTest({'type': 'reply_delta', 'text': 'Fresh'});
      expect(state.lastReply, 'Fresh');
      expect(state.lastReply, isNot(contains('old turn')));
    });
  });
}
