import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:uuid/uuid.dart';

import '../providers/app_state.dart';
import '../widgets/plan_draft_card.dart';
import 'home_shell.dart';
import '../services/web_title.dart';

class TextChatScreen extends StatefulWidget {
  const TextChatScreen({super.key, this.sessionId});

  final String? sessionId;

  @override
  State<TextChatScreen> createState() => _TextChatScreenState();
}

class _TextChatScreenState extends State<TextChatScreen> {
  final _controller = TextEditingController();
  final _messages = <Map<String, dynamic>>[];
  late final String _sessionId;
  final _scrollController = ScrollController();

  Map<String, dynamic>? _planDraft;
  String? _lastWebTitle;

  @override
  void initState() {
    super.initState();
    _sessionId = widget.sessionId ?? const Uuid().v4();
    if (widget.sessionId != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _loadHistory();
      });
    }
  }

  Future<void> _loadHistory() async {
    final state = context.read<AppState>();
    try {
      final history = await state.loadConversationHistory(_sessionId);
      if (!mounted) return;
      setState(() {
        _messages
          ..clear()
          ..addAll(
            history.map(
              (turn) => {'role': turn['role'], 'text': turn['content']},
            ),
          );
      });
      _scrollToBottom();
    } catch (_) {}
  }

  Future<void> _send() async {
    final text = _controller.text.trim();
    if (text.isEmpty) return;

    setState(() {
      _messages.add({'role': 'user', 'text': text});
      _controller.clear();
    });

    _scrollToBottom();

    final state = context.read<AppState>();

    try {
      final res = await state.sendTextTurn(text, sessionId: _sessionId);

      final assistantText =
          (res['assistantMessage'] as String?) ?? (res['reply'] as String?);
      setState(() {
        if (assistantText != null && assistantText.trim().isNotEmpty) {
          _messages.add({
            'role': 'assistant',
            'text': assistantText.trim(),
            'tool_actions': res['tool_actions'],
          });
        }
        _planDraft = res['plan_draft'] as Map<String, dynamic>?;
      });

      _scrollToBottom();
    } catch (_) {
      if (!mounted) return;

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(state.turnError ?? 'Something went wrong.')),
      );
    }
  }

  Future<void> _confirmPlan() async {
    final state = context.read<AppState>();
    await state.confirmPlanDraft();

    if (mounted) {
      setState(() => _planDraft = null);

      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('Added to Today')));
    }
  }

  Future<void> _discardPlan() async {
    await context.read<AppState>().discardPlanDraft();

    if (mounted) {
      setState(() => _planDraft = null);
    }
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scrollController.hasClients) return;

      _scrollController.animateTo(
        _scrollController.position.maxScrollExtent + 140,
        duration: const Duration(milliseconds: 320),
        curve: Curves.easeOutCubic,
      );
    });
  }

  void _goToVoiceCompanion() {
    if (Navigator.of(context).canPop()) {
      Navigator.of(context).pop();
      return;
    }
    context.read<AppState>().goToTab(0);
  }

  void _syncWebTitle(String title) {
    if (!kIsWeb || _lastWebTitle == title) return;
    _lastWebTitle = title;
    setWebPageTitle(title);
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<AppState>(
      builder: (context, state, _) {
        _syncWebTitle('Text Chat · AiPal');
        return AiPalShellScaffold(
          title: 'Text mode',
          subtitle: 'Contextual chat',
          onNotificationsTap: () {
            context.read<AppState>().goToTab(2);
            if (Navigator.of(context).canPop()) {
              Navigator.of(context).pop();
            }
          },
          onProfileTap: () {
            context.read<AppState>().goToTab(3);
            if (Navigator.of(context).canPop()) {
              Navigator.of(context).pop();
            }
          },
          showMobileBottomNav: false,
          body: Stack(
            children: [
              const _SoftChatBackground(),
              Column(
                children: [
                  if (state.turnError != null)
                    Padding(
                      padding: const EdgeInsets.fromLTRB(20, 8, 20, 0),
                      child: _ErrorBanner(message: state.turnError!),
                    ),
                  if (state.companionMode != null ||
                      state.memoriesUsed.isNotEmpty ||
                      state.suggestedActions.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.fromLTRB(20, 10, 20, 0),
                      child: _TurnMetaPanel(
                        mode: state.companionMode,
                        emotion: state.companionEmotion,
                        memoriesUsed: state.memoriesUsed,
                        suggestedActions: state.suggestedActions,
                        confirmationPrompt: state.confirmationPrompt,
                      ),
                    ),
                  Expanded(
                    child: _messages.isEmpty && _planDraft == null
                        ? ListView(
                            controller: _scrollController,
                            padding: const EdgeInsets.fromLTRB(20, 28, 20, 156),
                            children: const [
                              SizedBox(height: 84),
                              _EmptyChatState(),
                            ],
                          )
                        : ListView.builder(
                            controller: _scrollController,
                            padding: const EdgeInsets.fromLTRB(20, 24, 20, 156),
                            itemCount:
                                _messages.length + (_planDraft != null ? 1 : 0),
                            itemBuilder: (context, i) {
                              if (_planDraft != null && i == _messages.length) {
                                return Padding(
                                  padding: const EdgeInsets.only(top: 16),
                                  child: PlanDraftCard(
                                    draft: _planDraft!,
                                    onConfirm: _confirmPlan,
                                    onDiscard: _discardPlan,
                                  ),
                                );
                              }

                              final m = _messages[i];
                              final isUser = m['role'] == 'user';
                              final tools = m['tool_actions'] as List?;

                              return _MessageBubble(
                                text: m['text'] as String,
                                isUser: isUser,
                                tools: tools,
                              );
                            },
                          ),
                  ),
                ],
              ),
              Positioned(
                left: 16,
                right: 16,
                bottom: 20,
                child: _MessageComposer(
                  controller: _controller,
                  onSend: _send,
                  onVoiceTap: _goToVoiceCompanion,
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _TurnMetaPanel extends StatelessWidget {
  const _TurnMetaPanel({
    required this.mode,
    required this.emotion,
    required this.memoriesUsed,
    required this.suggestedActions,
    required this.confirmationPrompt,
  });

  final String? mode;
  final Map<String, dynamic>? emotion;
  final List<Map<String, dynamic>> memoriesUsed;
  final List<Map<String, dynamic>> suggestedActions;
  final String? confirmationPrompt;

  @override
  Widget build(BuildContext context) {
    final chips = <Widget>[];
    if (mode != null) {
      chips.add(_MetaChip(label: mode!, icon: Icons.badge_outlined));
    }
    if (emotion != null) {
      chips.add(
        _MetaChip(
          label: '${emotion!['emotion'] ?? 'neutral'}',
          icon: Icons.favorite_outline_rounded,
        ),
      );
    }
    if (memoriesUsed.isNotEmpty) {
      chips.add(
        _MetaChip(
          label: '${memoriesUsed.length} memories used',
          icon: Icons.memory_rounded,
        ),
      );
    }

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFFF8F7F3),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: const Color(0xFFE6E1D6)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(spacing: 8, runSpacing: 8, children: chips),
          if (confirmationPrompt != null) ...[
            const SizedBox(height: 10),
            Text(
              confirmationPrompt!,
              style: const TextStyle(
                fontSize: 12.5,
                height: 1.45,
                color: Color(0xFF4B444D),
              ),
            ),
          ],
          if (suggestedActions.isNotEmpty) ...[
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: suggestedActions
                  .map(
                    (a) => _MetaChip(
                      label: a['label']?.toString() ?? 'Action',
                      icon: Icons.arrow_forward_rounded,
                    ),
                  )
                  .toList(),
            ),
          ],
        ],
      ),
    );
  }
}

class _MetaChip extends StatelessWidget {
  const _MetaChip({required this.label, required this.icon});

  final String label;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: const Color(0xFFE6E1D6)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 15, color: const Color(0xFFFFC815)),
          const SizedBox(width: 6),
          Text(
            label,
            style: const TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w700,
              color: Color(0xFF1B1C1A),
            ),
          ),
        ],
      ),
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
    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        constraints: const BoxConstraints(maxWidth: 680),
        margin: const EdgeInsets.only(bottom: 18),
        child: Column(
          crossAxisAlignment: isUser
              ? CrossAxisAlignment.end
              : CrossAxisAlignment.start,
          children: [
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: isUser
                    ? const Color(0xFF21262D)
                    : const Color(0xFFFCFBF8),
                border: isUser
                    ? null
                    : Border.all(color: const Color(0xFFE6E1D6)),
                borderRadius: BorderRadius.only(
                  topLeft: const Radius.circular(22),
                  topRight: const Radius.circular(22),
                  bottomLeft: Radius.circular(isUser ? 22 : 6),
                  bottomRight: Radius.circular(isUser ? 6 : 22),
                ),
                boxShadow: [
                  BoxShadow(
                    color: const Color(0xFF1A1F2C).withValues(alpha: 0.025),
                    blurRadius: 16,
                    offset: const Offset(0, 8),
                  ),
                ],
              ),
              child: Text(
                text,
                style: TextStyle(
                  fontSize: 15.5,
                  height: 1.5,
                  fontWeight: FontWeight.w500,
                  color: isUser ? Colors.white : const Color(0xFF1B1C1A),
                ),
              ),
            ),
            if (tools != null && tools!.isNotEmpty) ...[
              const SizedBox(height: 7),
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(
                    Icons.insights_rounded,
                    size: 14,
                    color: Color(0xFFFFC815),
                  ),
                  const SizedBox(width: 5),
                  Text(
                    tools!.join(' · '),
                    style: const TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                      color: Color(0xFF6D6655),
                    ),
                  ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _MessageComposer extends StatelessWidget {
  const _MessageComposer({
    required this.controller,
    required this.onSend,
    required this.onVoiceTap,
  });

  final TextEditingController controller;
  final VoidCallback onSend;
  final VoidCallback onVoiceTap;

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: const BoxConstraints(maxWidth: 720),
      margin: const EdgeInsets.symmetric(horizontal: 0),
      child: Center(
        child: Container(
          padding: const EdgeInsets.fromLTRB(16, 12, 10, 12),
          decoration: BoxDecoration(
            color: const Color(0xFFFCFBF8),
            borderRadius: BorderRadius.circular(999),
            border: Border.all(color: const Color(0xFFE6E1D6)),
            boxShadow: [
              BoxShadow(
                color: const Color(0xFF1A1F2C).withValues(alpha: 0.03),
                blurRadius: 22,
                offset: const Offset(0, 10),
              ),
            ],
          ),
          child: Row(
            children: [
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  color: const Color(0xFFF8F7F3),
                  shape: BoxShape.circle,
                  border: Border.all(color: const Color(0xFFE6E1D6)),
                ),
                child: const Icon(
                  Icons.add_rounded,
                  color: Color(0xFF575C6B),
                  size: 20,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: TextField(
                  controller: controller,
                  minLines: 1,
                  maxLines: 4,
                  textInputAction: TextInputAction.send,
                  textAlignVertical: TextAlignVertical.center,
                  onSubmitted: (_) => onSend(),
                  style: const TextStyle(
                    color: Colors.black,
                    fontWeight: FontWeight.w500,
                  ),
                  decoration: const InputDecoration(
                    hintText: 'Type your message...',
                    border: InputBorder.none,
                    isCollapsed: true,
                    contentPadding: EdgeInsets.zero,
                    hintStyle: TextStyle(
                      color: Color(0xFF6D6655),
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Material(
                color: const Color(0xFFF8F7F3),
                shape: const CircleBorder(),
                child: InkWell(
                  customBorder: const CircleBorder(),
                  onTap: onVoiceTap,
                  child: const SizedBox(
                    width: 40,
                    height: 40,
                    child: Icon(
                      Icons.mic_rounded,
                      color: Color(0xFF575C6B),
                      size: 19,
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 6),
              Material(
                color: const Color(0xFFFFC815),
                shape: const CircleBorder(),
                child: InkWell(
                  customBorder: const CircleBorder(),
                  onTap: onSend,
                  child: const SizedBox(
                    width: 44,
                    height: 44,
                    child: Icon(
                      Icons.send_rounded,
                      color: Colors.white,
                      size: 20,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _EmptyChatState extends StatelessWidget {
  const _EmptyChatState();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Container(
        constraints: const BoxConstraints(maxWidth: 420),
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: const Color(0xFFFCFBF8),
          borderRadius: BorderRadius.circular(28),
          border: Border.all(color: const Color(0xFFE6E1D6)),
          boxShadow: [
            BoxShadow(
              color: const Color(0xFF1A1F2C).withValues(alpha: 0.025),
              blurRadius: 18,
              offset: const Offset(0, 10),
            ),
          ],
        ),
        child: const Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.chat_bubble_outline_rounded,
              size: 28,
              color: Color(0xFFFFC815),
            ),
            SizedBox(height: 12),
            Text(
              'Start a conversation',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontFamily: 'Manrope',
                fontSize: 20,
                height: 1.2,
                fontWeight: FontWeight.w800,
                color: Color(0xFF1B1C1A),
              ),
            ),
            SizedBox(height: 6),
            Text(
              'Your messages will appear here in a soft, distraction-free thread.',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 13.5,
                height: 1.5,
                fontWeight: FontWeight.w500,
                color: Color(0xFF4B444D),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ErrorBanner extends StatelessWidget {
  const _ErrorBanner({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      constraints: const BoxConstraints(maxWidth: 720),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: const Color(0xFFFFF1F0),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(
          color: const Color(0xFFBA1A1A).withValues(alpha: 0.22),
        ),
      ),
      child: Text(
        message,
        style: const TextStyle(
          fontSize: 13,
          height: 1.4,
          fontWeight: FontWeight.w600,
          color: Color(0xFF8F1D1D),
        ),
      ),
    );
  }
}

class _SoftChatBackground extends StatelessWidget {
  const _SoftChatBackground();

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        Container(color: const Color(0xFFFAF9F5)),
        Positioned(
          top: -160,
          right: -140,
          child: _BlurBlob(
            color: const Color(0xFFFFC815).withValues(alpha: 0.08),
          ),
        ),
        Positioned(
          bottom: -170,
          left: -150,
          child: _BlurBlob(
            color: const Color(0xFF003B2B).withValues(alpha: 0.08),
          ),
        ),
      ],
    );
  }
}

class _BlurBlob extends StatelessWidget {
  const _BlurBlob({required this.color});

  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 520,
      height: 520,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        boxShadow: [BoxShadow(color: color, blurRadius: 120, spreadRadius: 60)],
      ),
    );
  }
}
