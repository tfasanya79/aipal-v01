import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:uuid/uuid.dart';

import '../config.dart';
import '../providers/app_state.dart';
import '../services/live_session.dart';
import '../services/web_title.dart';
import '../widgets/plan_draft_card.dart';

// --- AiPal Gemini-Inspired Light Theme Colors ---
const _background = Color(0xFFFFFFFF);
const _surface = Color(0xFFF0F4F9); // Light blue-grey ash tone
const _surfaceVariant = Color(0xFFE9EEF6);
const _primaryText = Color(0xFF1F1F1F);
const _secondaryText = Color(0xFF757575);
const _border = Color(0xFFE3E3E3);

// Cosmic AiPal Sparkle Gradient
const _aipalGradient = LinearGradient(
  colors: [Color(0xFF1A73E8), Color(0xFF8AB4F8), Color(0xFFC58AF9)],
  begin: Alignment.topLeft,
  end: Alignment.bottomRight,
);

class CompanionScreen extends StatefulWidget {
  const CompanionScreen({super.key});

  @override
  State<CompanionScreen> createState() => _CompanionScreenState();
}

class _CompanionScreenState extends State<CompanionScreen> {
  final _textController = TextEditingController();
  final _scrollController = ScrollController();
  final _messages = <Map<String, dynamic>>[];
  final _inlineSessionId = const Uuid().v4();
  String? _lastSyncedTranscript;
  String? _lastSyncedReply;
  int? _assistantMessageIndex;
  bool _textSendInFlight = false;
  String? _lastWebTitle;
  String? _homeToken;
  Future<Map<String, dynamic>>? _homeFuture;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        final state = context.read<AppState>();
        state.clearTurnError();
        state.syncWakeListener();
      }
    });
  }

  @override
  void dispose() {
    _textController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  String _statusLabel(LiveState live) {
    switch (live) {
      case LiveState.resting:
        return 'Ready';
      case LiveState.listening:
        return 'Listening';
      case LiveState.thinking:
        return 'Thinking';
      case LiveState.speaking:
        return 'Speaking';
      case LiveState.reconnecting:
        return 'Reconnecting';
      case LiveState.failed:
        return 'Failed';
    }
  }

  String _helperText(AppState state, LiveState live) {
    if (state.turnError != null) return 'Connection issue';
    if (kIsWeb && state.wakeWordEnabled) {
      return live == LiveState.resting ? 'Wake word ready' : 'Wake word active';
    }
    if (state.checkinBanner != null && live == LiveState.resting) {
      return state.checkinBanner!;
    }
    if (live == LiveState.speaking) return 'Interrupt anytime.';
    if (live == LiveState.reconnecting) return 'Reconnecting to voice';
    if (live == LiveState.failed) return 'Voice connection failed';
    if (live == LiveState.thinking) return 'Thinking';
    if (live == LiveState.listening) return 'Listening';
    return 'Voice ready';
  }

  String _sessionModeLabel(LiveState live, AppState state) {
    if (state.turnError != null) return 'Need attention';
    if (live == LiveState.resting) return 'Ready';
    if (state.lastReply != null && state.lastReply!.trim().isNotEmpty) {
      return 'AiPal is talking';
    }
    return _statusLabel(live);
  }

  Future<void> _handleClose(AppState state) async {
    if (state.liveSession.state != LiveState.resting) {
      await state.toggleLive();
    }
    state.goToTab(1);
  }

  void _syncWebTitle(String title) {
    if (!kIsWeb || _lastWebTitle == title) return;
    _lastWebTitle = title;
    setWebPageTitle(title);
  }

  Future<Map<String, dynamic>> _companionHomeFuture(AppState state) {
    if (_homeFuture == null || _homeToken != state.token) {
      _homeToken = state.token;
      _homeFuture = state.api.getCompanionHome();
    }
    return _homeFuture!;
  }

  Future<void> _sendText(AppState state) async {
    final text = _textController.text.trim();
    if (text.isEmpty) return;
    await _sendPrompt(state, text, clearComposer: true);
  }

  Future<void> _sendPrompt(
    AppState state,
    String text, {
    bool clearComposer = false,
  }) async {
    if (_textSendInFlight) return;
    _textSendInFlight = true;
    if (clearComposer) {
      _textController.clear();
    }
    _scrollToBottom();

    try {
      await state.submitCompanionTextTurn(
        text,
        conversationId: _inlineSessionId,
      );
      if (!mounted) return;
      _scrollToBottom();
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(state.turnError ?? 'Something went wrong.')),
      );
    } finally {
      _textSendInFlight = false;
    }
  }

  Future<void> _sendToolCommand(
    AppState state,
    String tool, {
    required String prompt,
    Map<String, dynamic>? extra,
  }) async {
    if (_textSendInFlight) return;
    _textSendInFlight = true;
    _scrollToBottom();

    try {
      await state.submitCompanionTextTurn(
        prompt,
        source: 'tool',
        sourceContext: {'tool': tool, if (extra != null) ...extra},
      );
      if (!mounted) return;
      _scrollToBottom();
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(state.turnError ?? 'Something went wrong.')),
      );
    } finally {
      _textSendInFlight = false;
    }
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scrollController.hasClients) return;
      _scrollController.animateTo(
        _scrollController.position.maxScrollExtent + 120,
        duration: const Duration(milliseconds: 280),
        curve: Curves.easeOutCubic,
      );
    });
  }

  bool _syncConversationMessages(AppState state, LiveState live) {
    final transcript = state.lastTranscript?.trim();
    final reply = state.lastReply?.trim();
    var changed = false;

    if (AppConfig.showLiveTranscript &&
        transcript != null &&
        transcript.isNotEmpty &&
        transcript != _lastSyncedTranscript &&
        live != LiveState.listening) {
      _messages.add({'role': 'user', 'text': transcript});
      _lastSyncedTranscript = transcript;
      _assistantMessageIndex = null;
      _lastSyncedReply = null;
      changed = true;
    }

    if (reply != null && reply.isNotEmpty && reply != _lastSyncedReply) {
      final index = _assistantMessageIndex;
      if (index != null &&
          index >= 0 &&
          index < _messages.length &&
          _messages[index]['role'] == 'assistant') {
        _messages[index] = {..._messages[index], 'text': reply};
      } else {
        _messages.add({'role': 'assistant', 'text': reply});
        _assistantMessageIndex = _messages.length - 1;
      }
      _lastSyncedReply = reply;
      changed = true;
    }

    if (changed) {
      _scrollToBottom();
    }
    return changed;
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<AppState>(
      builder: (context, state, _) {
        final live = state.liveSession.state;
        final isLive = live != LiveState.resting;
        final webTitle = isLive ? 'Audio Call · AiPal' : 'Companion · AiPal';
        final homeFuture = _companionHomeFuture(state);
        _syncWebTitle(webTitle);
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (!mounted) return;
          if (_syncConversationMessages(state, live)) {
            setState(() {});
          }
        });

        return Scaffold(
          backgroundColor: _background,
          appBar: PreferredSize(
            preferredSize: const Size.fromHeight(60),
            child: _AiPalAppBar(
              status: _statusLabel(live),
              live: live,
              onClose: () => unawaited(_handleClose(state)),
            ),
          ),
          body: SafeArea(
            child: LayoutBuilder(
              builder: (context, constraints) {
                final width = constraints.maxWidth > 820
                    ? 820.0
                    : constraints.maxWidth;

                return Center(
                  child: SizedBox(
                    width: width,
                    height: constraints.maxHeight,
                    child: _ChatBody(
                      state: state,
                      live: live,
                      homeFuture: homeFuture,
                      scrollController: _scrollController,
                      textController: _textController,
                      messages: state.companionMessages,
                      helperText: _helperText(state, live),
                      modeLabel: _sessionModeLabel(live, state),
                      onHomeAction: (prompt) =>
                          unawaited(_sendPrompt(state, prompt)),
                      onPlanDay: () => unawaited(
                        _sendToolCommand(
                          state,
                          'planner_engine',
                          prompt: 'Help me plan my day.',
                          extra: {'plan_kind': 'daily'},
                        ),
                      ),
                      onMorningBrief: () => unawaited(
                        _sendToolCommand(
                          state,
                          'morning_brief',
                          prompt: 'Give me my morning brief.',
                        ),
                      ),
                      onMeetingHelp: () => unawaited(
                        _sendToolCommand(
                          state,
                          'meeting_assistant',
                          prompt: 'Help me prepare for my next meeting.',
                        ),
                      ),
                      onProjectRoom: () => unawaited(
                        _sendToolCommand(
                          state,
                          'project_rooms',
                          prompt: 'Help me with a project room.',
                        ),
                      ),
                      onLifeMap: () => unawaited(
                        _sendToolCommand(
                          state,
                          'life_map',
                          prompt: 'Show me my Life Map.',
                        ),
                      ),
                      onOpenToday: () => state.goToTab(1),
                      onMicTap: () => unawaited(state.toggleLive()),
                      onSendText: () => unawaited(_sendText(state)),
                    ),
                  ),
                );
              },
            ),
          ),
        );
      },
    );
  }
}

class _AiPalAppBar extends StatelessWidget {
  const _AiPalAppBar({
    required this.status,
    required this.live,
    required this.onClose,
  });

  final String status;
  final LiveState live;
  final VoidCallback onClose;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      color: _background,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          IconButton(
            icon: const Icon(Icons.close_rounded, color: _secondaryText),
            onPressed: onClose,
            tooltip: 'Close',
          ),
          Row(
            children: [
              const ShaderMask(
                shaderCallback: _createGradientShader,
                child: Icon(
                  Icons.auto_awesome_rounded,
                  color: Colors.white,
                  size: 20,
                ),
              ),
              const SizedBox(width: 8),
              Text(
                live == LiveState.resting ? 'AiPal' : 'AiPal Live ($status)',
                style: const TextStyle(
                  color: _primaryText,
                  fontSize: 18,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ],
          ),
          const SizedBox(width: 48),
        ],
      ),
    );
  }
}

class _ChatBody extends StatelessWidget {
  const _ChatBody({
    required this.state,
    required this.live,
    required this.homeFuture,
    required this.scrollController,
    required this.textController,
    required this.messages,
    required this.helperText,
    required this.modeLabel,
    required this.onHomeAction,
    required this.onPlanDay,
    required this.onMorningBrief,
    required this.onMeetingHelp,
    required this.onProjectRoom,
    required this.onLifeMap,
    required this.onOpenToday,
    required this.onMicTap,
    required this.onSendText,
  });

  final AppState state;
  final LiveState live;
  final Future<Map<String, dynamic>> homeFuture;
  final ScrollController scrollController;
  final TextEditingController textController;
  final List<Map<String, dynamic>> messages;
  final String helperText;
  final String modeLabel;
  final ValueChanged<String> onHomeAction;
  final VoidCallback onPlanDay;
  final VoidCallback onMorningBrief;
  final VoidCallback onMeetingHelp;
  final VoidCallback onProjectRoom;
  final VoidCallback onLifeMap;
  final VoidCallback onOpenToday;
  final VoidCallback onMicTap;
  final VoidCallback onSendText;

  @override
  Widget build(BuildContext context) {
    final transcript = state.lastTranscript?.trim();
    final hasLiveTranscript =
        AppConfig.showLiveTranscript &&
        transcript != null &&
        transcript.isNotEmpty &&
        live == LiveState.listening;
    final showGreeting =
        messages.isEmpty && !hasLiveTranscript && live == LiveState.resting;

    return Column(
      children: [
        Expanded(
          child: ListView(
            controller: scrollController,
            padding: const EdgeInsets.fromLTRB(24, 16, 24, 20),
            physics: const BouncingScrollPhysics(),
            children: [
              if (showGreeting) ...[
                const SizedBox(height: 32),
                const _AiPalGreetingState(),
                const SizedBox(height: 20),
                _SuggestedActionsGrid(
                  onPlanDay: onPlanDay,
                  onMorningBrief: onMorningBrief,
                  onMeetingHelp: onMeetingHelp,
                  onProjectRoom: onProjectRoom,
                ),
                const SizedBox(height: 24),
                _CompanionHomePanel(future: homeFuture, onAction: onHomeAction),
              ] else ...[
                for (final message in messages)
                  _MessageBubble(
                    text: message['text'] as String? ?? '',
                    isUser: message['role'] == 'user',
                    tools: message['tool_actions'] as List?,
                  ),
                if (hasLiveTranscript)
                  _MessageBubble(text: transcript, isUser: true),
                if (live != LiveState.resting) ...[
                  const SizedBox(height: 16),
                  _VoiceStateBanner(
                    live: live,
                    mode: modeLabel,
                    helper: helperText,
                  ),
                ],
                if (state.turnError != null) ...[
                  const SizedBox(height: 16),
                  _ErrorPanel(errorText: state.turnError!),
                ],
                if (live == LiveState.resting &&
                    state.nextOpenTask != null) ...[
                  const SizedBox(height: 16),
                  _NextTaskCard(
                    title: '${state.nextOpenTask!['title']}',
                    onTap: onOpenToday,
                  ),
                ],
                if (state.pendingPlanDraft != null) ...[
                  const SizedBox(height: 16),
                  PlanDraftCard(
                    draft: state.pendingPlanDraft!,
                    onConfirm: () => state.confirmPlanDraft(),
                    onDiscard: () => state.discardPlanDraft(),
                  ),
                ],
              ],
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(24, 8, 24, 16),
          child: SafeArea(
            top: false,
            child: _InlineComposer(
              controller: textController,
              live: live,
              onMicTap: onMicTap,
              onSend: onSendText,
            ),
          ),
        ),
      ],
    );
  }
}

class _AiPalGreetingState extends StatelessWidget {
  const _AiPalGreetingState();

  @override
  Widget build(BuildContext context) {
    return const Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ShaderMask(
          shaderCallback: _createGradientShader,
          child: Text(
            'Hello, friend',
            style: TextStyle(
              color: Colors.white,
              fontSize: 36,
              fontWeight: FontWeight.w500,
              letterSpacing: -0.5,
            ),
          ),
        ),
        SizedBox(height: 4),
        Text(
          'How can I help you today?',
          style: TextStyle(
            color: Color(0xFFC4C7C5),
            fontSize: 36,
            fontWeight: FontWeight.w500,
            letterSpacing: -0.5,
          ),
        ),
      ],
    );
  }
}

class _InlineComposer extends StatelessWidget {
  const _InlineComposer({
    required this.controller,
    required this.live,
    required this.onMicTap,
    required this.onSend,
  });

  final TextEditingController controller;
  final LiveState live;
  final VoidCallback onMicTap;
  final VoidCallback onSend;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: Container(
            constraints: const BoxConstraints(minHeight: 52),
            padding: const EdgeInsets.fromLTRB(20, 6, 8, 6),
            decoration: BoxDecoration(
              color: _surface,
              borderRadius: BorderRadius.circular(28),
              border: Border.all(color: _border),
            ),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: controller,
                    minLines: 1,
                    maxLines: 4,
                    textInputAction: TextInputAction.send,
                    onSubmitted: (_) => onSend(),
                    style: const TextStyle(color: _primaryText, fontSize: 16),
                    decoration: InputDecoration(
                      hintText: 'Ask AiPal...',
                      border: InputBorder.none,
                      isCollapsed: true,
                      hintStyle: TextStyle(
                        color: _secondaryText.withValues(alpha: 0.8),
                        fontSize: 16,
                      ),
                    ),
                  ),
                ),
                Material(
                  color: Colors.transparent,
                  shape: const CircleBorder(),
                  child: InkWell(
                    onTap: onSend,
                    customBorder: const CircleBorder(),
                    child: Container(
                      width: 40,
                      height: 40,
                      decoration: const BoxDecoration(
                        shape: BoxShape.circle,
                        gradient: _aipalGradient,
                      ),
                      child: const Icon(
                        Icons.send_rounded,
                        color: Colors.white,
                        size: 19,
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(width: 10),
        InkWell(
          onTap: onMicTap,
          customBorder: const CircleBorder(),
          child: Container(
            width: 52,
            height: 52,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: live != LiveState.resting ? _aipalGradient : null,
              color: live == LiveState.resting ? _surface : null,
              border: live == LiveState.resting
                  ? Border.all(color: _border)
                  : null,
            ),
            child: Icon(
              live != LiveState.resting
                  ? Icons.stop_rounded
                  : Icons.mic_none_rounded,
              color: live != LiveState.resting ? Colors.white : _primaryText,
              size: 24,
            ),
          ),
        ),
      ],
    );
  }
}

class _SuggestedActionsGrid extends StatelessWidget {
  const _SuggestedActionsGrid({
    required this.onPlanDay,
    required this.onMorningBrief,
    required this.onMeetingHelp,
    required this.onProjectRoom,
  });

  final VoidCallback onPlanDay;
  final VoidCallback onMorningBrief;
  final VoidCallback onMeetingHelp;
  final VoidCallback onProjectRoom;

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      physics: const BouncingScrollPhysics(),
      child: Row(
        children: [
          _PromptGridCard(
            icon: Icons.calendar_today_rounded,
            label: 'Plan Day',
            onTap: onPlanDay,
          ),
          _PromptGridCard(
            icon: Icons.wb_sunny_rounded,
            label: 'Briefing',
            onTap: onMorningBrief,
          ),
          _PromptGridCard(
            icon: Icons.chat_bubble_outline_rounded,
            label: 'Meeting Assist',
            onTap: onMeetingHelp,
          ),
          _PromptGridCard(
            icon: Icons.layers_rounded,
            label: 'Project Space',
            onTap: onProjectRoom,
          ),
        ],
      ),
    );
  }
}

class _PromptGridCard extends StatelessWidget {
  const _PromptGridCard({
    required this.icon,
    required this.label,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(right: 8),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Ink(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          decoration: BoxDecoration(
            color: _surface,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: _border, width: 0.5),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icon, color: _secondaryText, size: 16),
              const SizedBox(width: 8),
              Text(
                label,
                style: const TextStyle(
                  color: _primaryText,
                  fontSize: 13,
                  fontWeight: FontWeight.w400,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _CompanionHomePanel extends StatelessWidget {
  const _CompanionHomePanel({required this.future, required this.onAction});

  final Future<Map<String, dynamic>> future;
  final ValueChanged<String> onAction;

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<Map<String, dynamic>>(
      future: future,
      builder: (context, snapshot) {
        final data = snapshot.data;
        final cards = (data?['cards'] as List? ?? [])
            .whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList();
        final loading = snapshot.connectionState == ConnectionState.waiting;
        final message = data?['message']?.toString().trim();
        final hasMessage = message != null && message.isNotEmpty;

        if (loading) return const _HomeSkeleton();

        return Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: _surfaceVariant,
            borderRadius: BorderRadius.circular(24),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const ShaderMask(
                    shaderCallback: _createGradientShader,
                    child: Icon(
                      Icons.bubble_chart_rounded,
                      color: Colors.white,
                      size: 20,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Text(
                    'Your Daily Brief',
                    style: TextStyle(
                      color: _primaryText.withValues(alpha: 0.9),
                      fontSize: 15,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Text(
                hasMessage ? message : 'Your schedule is currently clear.',
                style: const TextStyle(
                  color: _primaryText,
                  fontSize: 15,
                  height: 1.5,
                ),
              ),
              if (cards.isNotEmpty) ...[
                const SizedBox(height: 16),
                SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  child: Row(
                    children: cards.take(4).map((card) {
                      return Padding(
                        padding: const EdgeInsets.only(right: 8),
                        child: ActionChip(
                          backgroundColor: _surface,
                          side: BorderSide.none,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(16),
                          ),
                          label: Text(
                            card['title']?.toString() ?? 'Action',
                            style: const TextStyle(
                              color: _primaryText,
                              fontSize: 13,
                            ),
                          ),
                          onPressed: () {
                            final prompt = card['prompt']?.toString();
                            if (prompt != null) onAction(prompt.trim());
                          },
                        ),
                      );
                    }).toList(),
                  ),
                ),
              ],
            ],
          ),
        );
      },
    );
  }
}

class _MessageBubble extends StatelessWidget {
  const _MessageBubble({required this.text, required this.isUser, this.tools});

  final String text;
  final bool isUser;
  final List? tools;

  @override
  Widget build(BuildContext context) {
    final screenWidth = MediaQuery.sizeOf(context).width;
    final maxBubbleWidth = screenWidth < 520 ? screenWidth * 0.78 : 560.0;

    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: maxBubbleWidth),
        child: Container(
          margin: const EdgeInsets.symmetric(vertical: 6),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          decoration: BoxDecoration(
            color: isUser ? _surfaceVariant : _surface,
            borderRadius: BorderRadius.only(
              topLeft: const Radius.circular(18),
              topRight: const Radius.circular(18),
              bottomLeft: Radius.circular(isUser ? 18 : 6),
              bottomRight: Radius.circular(isUser ? 6 : 18),
            ),
            border: Border.all(color: _border, width: 0.6),
          ),
          child: Column(
            crossAxisAlignment: isUser
                ? CrossAxisAlignment.end
                : CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                text,
                style: const TextStyle(
                  color: _primaryText,
                  fontSize: 14.5,
                  height: 1.42,
                  fontWeight: FontWeight.w400,
                ),
              ),
              if (tools != null && tools!.isNotEmpty) ...[
                const SizedBox(height: 6),
                Text(
                  tools!.join(' · '),
                  style: TextStyle(
                    color: _secondaryText.withValues(alpha: 0.75),
                    fontSize: 11,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _VoiceStateBanner extends StatelessWidget {
  const _VoiceStateBanner({
    required this.live,
    required this.mode,
    required this.helper,
  });

  final LiveState live;
  final String mode;
  final String helper;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: _surfaceVariant,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        children: [
          if (live == LiveState.thinking)
            const SizedBox(
              width: 20,
              height: 20,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                color: Colors.blueAccent,
              ),
            )
          else
            const Icon(Icons.blur_on_rounded, color: Colors.blueAccent),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  mode,
                  style: const TextStyle(
                    color: _primaryText,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                Text(
                  helper,
                  style: const TextStyle(color: _secondaryText, fontSize: 13),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _HomeSkeleton extends StatelessWidget {
  const _HomeSkeleton();
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: _surfaceVariant,
        borderRadius: BorderRadius.circular(24),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            height: 16,
            width: 140,
            decoration: BoxDecoration(
              color: _surface,
              borderRadius: BorderRadius.circular(8),
            ),
          ),
          const SizedBox(height: 12),
          Container(
            height: 14,
            width: double.infinity,
            decoration: BoxDecoration(
              color: _surface,
              borderRadius: BorderRadius.circular(8),
            ),
          ),
        ],
      ),
    );
  }
}

class _NextTaskCard extends StatelessWidget {
  const _NextTaskCard({required this.title, required this.onTap});
  final String title;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      tileColor: _surface,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      title: Text(title, style: const TextStyle(color: _primaryText)),
      trailing: const Icon(Icons.chevron_right_rounded, color: _secondaryText),
      onTap: onTap,
    );
  }
}

class _ErrorPanel extends StatelessWidget {
  const _ErrorPanel({required this.errorText});
  final String errorText;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFFFFEBEE),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.redAccent.withValues(alpha: 0.2)),
      ),
      child: Text(
        errorText,
        style: const TextStyle(color: Colors.redAccent, fontSize: 14),
      ),
    );
  }
}

Shader _createGradientShader(Rect bounds) =>
    _aipalGradient.createShader(bounds);
