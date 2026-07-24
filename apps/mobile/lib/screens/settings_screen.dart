import 'dart:convert';
import 'dart:ui';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../providers/app_state.dart';
import '../services/calendar_service.dart';
import '../services/notification_service.dart';
import 'splash_screen.dart';

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final profile = state.profile;

    final email = profile?['email']?.toString() ?? '';
    final wakeName = profile?['wake_name']?.toString() ?? '—';
    final checkInEnabled = profile?['checkin_enabled'] as bool? ?? true;

    Future<void> signOut() async {
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('Sign out of browser session?'),
          content: const Text(
            'This clears the saved web session so AiPal will ask for a fresh login next time.',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Sign out'),
            ),
          ],
        ),
      );

      if (confirmed != true || !context.mounted) return;

      await context.read<AppState>().signOut();
      if (!context.mounted) return;

      Navigator.of(context).pushAndRemoveUntil(
        MaterialPageRoute(builder: (_) => const SplashScreen()),
        (route) => false,
      );
    }

    return Scaffold(
      backgroundColor: const Color(0xFFFAF9F5),
      body: Stack(
        children: [
          const _SettingsAtmosphere(),

          Row(
            children: [
              Expanded(
                child: CustomScrollView(
                  slivers: [
                    SliverPadding(
                      padding: const EdgeInsets.fromLTRB(40, 24, 40, 72),
                      sliver: SliverList(
                        delegate: SliverChildListDelegate([
                          const _SectionLabel('Identity'),
                          _GlassCard(
                            child: Column(
                              children: [
                                _IdentityRow(
                                  icon: Icons.mail_outline_rounded,
                                  label: 'Registered Email',
                                  value: email.isEmpty
                                      ? 'No email found'
                                      : email,
                                ),
                                const _SoftDivider(),
                                _IdentityRow(
                                  icon: Icons.waving_hand_rounded,
                                  label: 'Wake name',
                                  value: wakeName,
                                ),
                              ],
                            ),
                          ),

                          const SizedBox(height: 34),

                          const _SectionLabel('Voice & Interaction'),
                          _GlassCard(
                            child: Column(
                              children: [
                                _SwitchSettingRow(
                                  icon: Icons.record_voice_over_rounded,
                                  title: 'Listen for "Hi Pal"',
                                  subtitle: kIsWeb
                                      ? 'On web, turn this on and say Hi Pal while Live is listening.'
                                      : state.wakeWordError != null
                                      ? state.wakeWordError!
                                      : defaultTargetPlatform ==
                                            TargetPlatform.android
                                      ? 'Say Hi Pal anytime to start Live. Shows a listening notification while enabled.'
                                      : 'On the Companion tab, say Hi Pal to start Live hands-free.',
                                  value: state.wakeWordEnabled,
                                  enabled: true,
                                  isError: state.wakeWordError != null,
                                  onChanged: (v) => state.setWakeWordEnabled(v),
                                ),
                                const _SoftDivider(),
                                _SwitchSettingRow(
                                  icon: Icons.notifications_active_outlined,
                                  title: 'Check-in enabled',
                                  subtitle:
                                      'Allow AiPal to proactively check on your status.',
                                  value: checkInEnabled,
                                  onChanged: (v) => state.updateProfile({
                                    'checkin_enabled': v,
                                  }),
                                ),
                                const _SoftDivider(),
                                const _VoiceChoiceRow(),
                              ],
                            ),
                          ),

                          const SizedBox(height: 34),

                          const _SectionLabel('Connectivity'),
                          LayoutBuilder(
                            builder: (context, constraints) {
                              final wide = constraints.maxWidth >= 760;

                              final morning = _ConnectivityCard(
                                icon: Icons.update_rounded,
                                title: 'Reschedule morning brief',
                                subtitle: 'Currently scheduled for 08:00 AM.',
                                action: 'Manage timing',
                                onTap: () => NotificationService.instance
                                    .scheduleMorningBrief(hour: 8, minute: 0),
                              );

                              final calendar = _ConnectivityCard(
                                icon: Icons.calendar_month_rounded,
                                title: 'Import today\'s calendar',
                                subtitle: 'Sync events from Google or Outlook.',
                                action: 'Sync now',
                                badge: 'v2.1',
                                onTap: () async {
                                  final events = await CalendarService()
                                      .fetchTodayEvents();

                                  if (context.mounted && events.isNotEmpty) {
                                    final n = await context
                                        .read<AppState>()
                                        .api
                                        .importCalendar(events);

                                    if (context.mounted) {
                                      ScaffoldMessenger.of(
                                        context,
                                      ).showSnackBar(
                                        SnackBar(
                                          content: Text(
                                            'Imported $n calendar events',
                                          ),
                                        ),
                                      );
                                    }
                                  }
                                },
                              );

                              final spotify = _ConnectivityCard(
                                icon: Icons.headphones_rounded,
                                iconColor: const Color(0xFF1DB954),
                                title: 'Connect Spotify',
                                subtitle:
                                    'Control playback with voice commands.',
                                action: 'Authorize Spotify',
                                badge: 'v2.1',
                                darkAction: true,
                                onTap: () async {
                                  final uri = Uri.parse(
                                    'https://43.160.220.9.sslip.io/privacy-policy.html',
                                  );
                                  await launchUrl(uri);
                                },
                              );

                              if (!wide) {
                                return Column(
                                  children: [
                                    morning,
                                    const SizedBox(height: 16),
                                    calendar,
                                    const SizedBox(height: 16),
                                    spotify,
                                  ],
                                );
                              }

                              return Column(
                                children: [
                                  Row(
                                    children: [
                                      Expanded(child: morning),
                                      const SizedBox(width: 24),
                                      Expanded(child: calendar),
                                    ],
                                  ),
                                  const SizedBox(height: 24),
                                  spotify,
                                ],
                              );
                            },
                          ),

                          //   const SizedBox(height: 56),

                          //   const _SectionLabel('Privacy & Data'),
                          //   _QuickNavCard(
                          //     icon: Icons.psychology_rounded,
                          //     title: 'Memory Control Center',
                          //     subtitle: 'Edit, pause, export, or clear saved context.',
                          //     action: 'Open',
                          //     onTap: () {
                          //       Navigator.of(context).push(
                          //         MaterialPageRoute(
                          //           builder: (_) => const MemoryControlCenterScreen(),
                          //       ),
                          //     );
                          //   },
                          // ),
                          //   const SizedBox(height: 14),
                          //   _QuickNavCard(
                          //     icon: Icons.timeline_rounded,
                          //     title: 'Memory Timeline',
                          //     subtitle: 'Browse wins, events, concerns, and follow-ups over time.',
                          //     action: 'Open',
                          //     onTap: () {
                          //       Navigator.of(context).push(
                          //         MaterialPageRoute(
                          //           builder: (_) => const MemoryTimelineScreen(),
                          //         ),
                          //       );
                          //     },
                          //   ),
                          //   const SizedBox(height: 14),
                          //   _QuickNavCard(
                          //     icon: Icons.device_hub_rounded,
                          //     title: 'Knowledge Graph',
                          //     subtitle: 'See people, projects, topics, and linked memories.',
                          //     action: 'Open',
                          //     onTap: () {
                          //       Navigator.of(context).push(
                          //         MaterialPageRoute(
                          //           builder: (_) => const KnowledgeGraphScreen(),
                          //         ),
                          //       );
                          //     },
                          //   ),
                          //   const SizedBox(height: 14),
                          //   _QuickNavCard(
                          //     icon: Icons.file_download_rounded,
                          //     title: 'Export memories',
                          //     subtitle: 'Download stored companion memory for your records.',
                          //     action: 'Export',
                          //     onTap: exportMemories,
                          //   ),
                          //   const SizedBox(height: 14),
                          //   _QuickNavCard(
                          //     icon: Icons.delete_forever_rounded,
                          //     title: 'Clear conversation history',
                          //     subtitle: 'Delete companion conversation history from this browser.',
                          //     action: 'Clear',
                          //     onTap: clearConversationHistory,
                          //   ),

                          //   const SizedBox(height: 34),

                          //   const _SectionLabel('Companion Library'),
                          //   _QuickNavCard(
                          //     icon: Icons.flag_rounded,
                          //     title: 'Goals',
                          //     subtitle: 'Create and manage the goals AiPal should support.',
                          //     action: 'Open',
                          //     onTap: () {
                          //       Navigator.of(context).push(
                          //         MaterialPageRoute(
                          //           builder: (_) => const GoalsScreen(),
                          //         ),
                          //       );
                          //     },
                          //   ),
                          //   const SizedBox(height: 14),
                          //   _QuickNavCard(
                          //     icon: Icons.auto_stories_rounded,
                          //     title: 'Reflections',
                          //     subtitle: 'Log daily and weekly check-ins, wins, and lessons.',
                          //     action: 'Open',
                          //     onTap: () {
                          //       Navigator.of(context).push(
                          //         MaterialPageRoute(
                          //           builder: (_) => const ReflectionScreen(),
                          //       ),
                          //     );
                          //   },
                          //   ),
                          //   const SizedBox(height: 14),
                          //   _QuickNavCard(
                          //     icon: Icons.insights_rounded,
                          //     title: 'Insights',
                          //     subtitle: 'Review emotional trends, goals, memories, and companion themes.',
                          //     action: 'Open',
                          //     onTap: () {
                          //       Navigator.of(context).push(
                          //         MaterialPageRoute(
                          //           builder: (_) => const InsightsScreen(),
                          //       ),
                          //     );
                          //   },
                          //   ),
                          //   const SizedBox(height: 14),
                          //   _QuickNavCard(
                          //     icon: Icons.psychology_alt_rounded,
                          //     title: 'Coach',
                          //     subtitle: 'Decision coaching, frameworks, and strategic thinking.',
                          //     action: 'Open',
                          //     onTap: () {
                          //       Navigator.of(context).push(
                          //         MaterialPageRoute(
                          //           builder: (_) => const CoachScreen(),
                          //         ),
                          //       );
                          //     },
                          //   ),
                          //   const SizedBox(height: 14),
                          //   _QuickNavCard(
                          //     icon: Icons.trending_up_rounded,
                          //     title: 'Growth Plans',
                          //     subtitle: 'Create 30/60/90-day plans tied to a goal.',
                          //     action: 'Open',
                          //     onTap: () {
                          //       Navigator.of(context).push(
                          //         MaterialPageRoute(
                          //           builder: (_) => const GrowthPlanScreen(),
                          //         ),
                          //       );
                          //     },
                          //   ),
                          //   const SizedBox(height: 14),
                          //   _QuickNavCard(
                          //     icon: Icons.fact_check_rounded,
                          //     title: 'Accountability',
                          //     subtitle: 'Review blockers, habits, and weekly progress.',
                          //     action: 'Open',
                          //     onTap: () {
                          //       Navigator.of(context).push(
                          //         MaterialPageRoute(
                          //           builder: (_) => const AccountabilityScreen(),
                          //         ),
                          //       );
                          //     },
                          //   ),
                          //   const SizedBox(height: 14),
                          //   _QuickNavCard(
                          //     icon: Icons.fitness_center_rounded,
                          //     title: 'Habit Intelligence',
                          //     subtitle: 'Track habits lightly and avoid over-logging.',
                          //     action: 'Open',
                          //     onTap: () {
                          //       Navigator.of(context).push(
                          //         MaterialPageRoute(
                          //           builder: (_) => const HabitIntelligenceScreen(),
                          //         ),
                          //       );
                          //     },
                          //   ),
                          //   const SizedBox(height: 34),

                          //   const _SectionLabel('AiPal OS'),
                          //   _QuickNavCard(
                          //     icon: Icons.dashboard_rounded,
                          //     title: 'Life Dashboard',
                          //     subtitle: 'A single view of goals, mood, and proactive prompts.',
                          //     action: 'Open',
                          //     onTap: () {
                          //       Navigator.of(context).push(
                          //         MaterialPageRoute(
                          //           builder: (_) => const LifeDashboardScreen(),
                          //         ),
                          //       );
                          //     },
                          //   ),
                          //   const SizedBox(height: 14),
                          //   _QuickNavCard(
                          //     icon: Icons.tune_rounded,
                          //     title: 'Companion Preferences',
                          //     subtitle: 'Adjust tone, humor, quiet hours, and proactive nudges.',
                          //     action: 'Open',
                          //     onTap: () {
                          //       Navigator.of(context).push(
                          //         MaterialPageRoute(
                          //           builder: (_) => const CompanionPreferencesScreen(),
                          //         ),
                          //       );
                          //     },
                          //   ),
                          //   const SizedBox(height: 14),
                          //   _QuickNavCard(
                          //     icon: Icons.cloud_queue_rounded,
                          //     title: 'Connected Sources',
                          //     subtitle: 'Email, calendar, documents, WhatsApp, and more.',
                          //     action: 'Open',
                          //     onTap: () {
                          //       Navigator.of(context).push(
                          //         MaterialPageRoute(
                          //           builder: (_) => const ConnectedSourcesScreen(),
                          //         ),
                          //       );
                          //     },
                          //   ),
                          //   const SizedBox(height: 14),
                          //   _QuickNavCard(
                          //     icon: Icons.business_center_rounded,
                          //     title: 'Business Context',
                          //     subtitle: 'Projects, goals, risks, opportunities, and events.',
                          //     action: 'Open',
                          //     onTap: () {
                          //       Navigator.of(context).push(
                          //         MaterialPageRoute(
                          //           builder: (_) => const BusinessContextScreen(),
                          //         ),
                          //       );
                          //     },
                          //   ),
                          //   const SizedBox(height: 14),
                          //   _QuickNavCard(
                          //     icon: Icons.event_available_rounded,
                          //     title: 'Commitments',
                          //     subtitle: 'Meetings, deadlines, and follow-ups.',
                          //     action: 'Open',
                          //     onTap: () {
                          //       Navigator.of(context).push(
                          //         MaterialPageRoute(
                          //           builder: (_) => const CommitmentsScreen(),
                          //         ),
                          //       );
                          //     },
                          //   ),
                          //   const SizedBox(height: 14),
                          //   _QuickNavCard(
                          //     icon: Icons.privacy_tip_rounded,
                          //     title: 'Source Privacy',
                          //     subtitle: 'Review connected sources and remove imported data.',
                          //     action: 'Open',
                          //     onTap: () {
                          //       Navigator.of(context).push(
                          //         MaterialPageRoute(
                          //           builder: (_) => const SourcePrivacyScreen(),
                          //         ),
                          //       );
                          //     },
                          //   ),
                          const SizedBox(height: 34),

                          if (kIsWeb) ...[
                            _AccountActionCard(
                              title: 'Browser session',
                              subtitle:
                                  'Clear the saved web login and return to the sign-in flow.',
                              action: 'Sign out',
                              onTap: signOut,
                            ),
                            const SizedBox(height: 20),
                          ],

                          const _SettingsFooter(),
                        ]),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _SectionLabel extends StatelessWidget {
  const _SectionLabel(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(left: 14, bottom: 14),
      child: Text(
        text.toUpperCase(),
        style: const TextStyle(
          fontSize: 12,
          fontWeight: FontWeight.w900,
          letterSpacing: 1.7,
          color: Color(0xFFFFC815),
        ),
      ),
    );
  }
}

class _GlassCard extends StatelessWidget {
  const _GlassCard({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(48),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 40, sigmaY: 40),
        child: Container(
          padding: const EdgeInsets.all(24),
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: 0.40),
            borderRadius: BorderRadius.circular(48),
            border: Border.all(color: Colors.white.withValues(alpha: 0.80)),
            boxShadow: [
              BoxShadow(
                color: const Color(0xFF1A1F2C).withValues(alpha: 0.04),
                blurRadius: 60,
                offset: const Offset(0, 30),
              ),
            ],
          ),
          child: child,
        ),
      ),
    );
  }
}

class _IdentityRow extends StatelessWidget {
  const _IdentityRow({
    required this.icon,
    required this.label,
    required this.value,
  });

  final IconData icon;
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        _RoundIcon(icon: icon, background: const Color(0xFFE9E8E4)),
        const SizedBox(width: 24),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                label,
                style: const TextStyle(
                  fontSize: 14,
                  color: Color(0xFF575C6B),
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 5),
              Text(
                value,
                style: const TextStyle(
                  fontFamily: 'Manrope',
                  fontSize: 18,
                  fontWeight: FontWeight.w800,
                  color: Color(0xFF1B1C1A),
                ),
              ),
            ],
          ),
        ),
        const Icon(Icons.edit_rounded, color: Color(0xFFE8DFAF)),
      ],
    );
  }
}

class _SwitchSettingRow extends StatelessWidget {
  const _SwitchSettingRow({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.value,
    required this.onChanged,
    this.enabled = true,
    this.isError = false,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final bool value;
  final ValueChanged<bool> onChanged;
  final bool enabled;
  final bool isError;

  @override
  Widget build(BuildContext context) {
    return Opacity(
      opacity: enabled ? 1 : 0.55,
      child: Row(
        children: [
          _RoundIcon(
            icon: icon,
            background: const Color(0xFFFFF2B8).withValues(alpha: 0.65),
          ),
          const SizedBox(width: 24),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    fontFamily: 'Manrope',
                    fontSize: 18,
                    fontWeight: FontWeight.w800,
                    color: Color(0xFF1B1C1A),
                  ),
                ),
                const SizedBox(height: 5),
                Text(
                  subtitle,
                  style: TextStyle(
                    fontSize: 13,
                    height: 1.4,
                    color: isError
                        ? const Color(0xFFBA1A1A)
                        : const Color(0xFF575C6B),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 20),
          _PremiumSwitch(value: value, enabled: enabled, onChanged: onChanged),
        ],
      ),
    );
  }
}

class _VoiceChoiceRow extends StatefulWidget {
  const _VoiceChoiceRow();

  @override
  State<_VoiceChoiceRow> createState() => _VoiceChoiceRowState();
}

class _VoiceChoiceRowState extends State<_VoiceChoiceRow> {
  static const _fallbackVoices = <Map<String, String>>[
    {
      'id': 'calm_female',
      'name': 'Calm Female',
      'style': 'Warm, calm, and steady',
      'provider': 'local',
    },
    {
      'id': 'calm_male',
      'name': 'Calm Male',
      'style': 'Relaxed, grounded, and patient',
      'provider': 'local',
    },
    {
      'id': 'coach',
      'name': 'Coach',
      'style': 'Direct, focused, and strategic',
      'provider': 'local',
    },
    {
      'id': 'friendly',
      'name': 'Friendly',
      'style': 'Warm and friendly',
      'provider': 'local',
    },
    {
      'id': 'professional',
      'name': 'Professional',
      'style': 'Clear, concise, and composed',
      'provider': 'local',
    },
    {
      'id': 'builder',
      'name': 'Builder',
      'style': 'Startup-focused and execution-minded',
      'provider': 'local',
    },
    {
      'id': 'energetic',
      'name': 'Energetic',
      'style': 'Bright, upbeat, and conversational',
      'provider': 'local',
    },
    {
      'id': 'gentle',
      'name': 'Gentle',
      'style': 'Soft, reflective, and reassuring',
      'provider': 'local',
    },
  ];

  String _selected = 'calm_female';
  List<Map<String, dynamic>> _voices = _fallbackVoices;
  bool _loading = true;
  bool _saving = false;
  bool _previewing = false;
  final AudioPlayer _player = AudioPlayer();

  bool _hasVoice(String id) => _voices.any((voice) => voice['id'] == id);

  String _voiceName(String id) {
    return _voices
        .firstWhere(
          (voice) => voice['id'] == id,
          orElse: () => const {'name': 'Default'},
        )['name']
        .toString();
  }

  Map<String, dynamic> get _selectedVoice => _voices.firstWhere(
    (voice) => voice['id'] == _selected,
    orElse: () => _fallbackVoices.first,
  );

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _player.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final api = context.read<AppState>().api;
      final results = await Future.wait([
        api.getCompanionPreferences(),
        api.getTtsVoices(),
      ]);
      final prefs = results[0] as Map<String, dynamic>;
      final voices = (results[1] as List<Map<String, dynamic>>)
          .where((voice) => (voice['id']?.toString() ?? '').isNotEmpty)
          .toList();
      if (!mounted) return;
      setState(() {
        if (voices.isNotEmpty) {
          _voices = voices;
        }
        _selected =
            prefs['voice_profile']?.toString() ??
            prefs['tts_voice']?.toString() ??
            'calm_female';
        if (!_hasVoice(_selected)) {
          _selected = 'calm_female';
        }
        _loading = false;
      });
    } catch (_) {
      if (mounted) {
        setState(() => _loading = false);
      }
    }
  }

  Future<void> _save(String value) async {
    setState(() {
      _selected = value;
      _saving = true;
    });
    try {
      await context.read<AppState>().api.updateCompanionPreferences({
        'voice_profile': value,
        'tts_voice': value,
      });
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Voice changed to ${_voiceName(value)}')),
      );
    } finally {
      if (mounted) {
        setState(() => _saving = false);
      }
    }
  }

  Future<void> _preview() async {
    final previewText = _selectedVoice['preview_text']?.toString().trim() ?? '';
    if (previewText.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Voice preview is unavailable.')),
      );
      return;
    }
    setState(() => _previewing = true);
    try {
      final response = await context.read<AppState>().api.tts(
        previewText,
        voice: _selected,
      );
      final audio = response['audio_base64'] as String?;
      final mime = response['audio_mime'] as String? ?? 'audio/wav';
      if (audio == null || audio.isEmpty) return;
      await _player.stop();
      await _player.play(BytesSource(base64Decode(audio), mimeType: mime));
    } finally {
      if (mounted) {
        setState(() => _previewing = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    Widget controls({double? width}) {
      return SizedBox(
        width: width,
        child: Row(
          children: [
            Expanded(
              child: DropdownButtonFormField<String>(
                initialValue: _hasVoice(_selected) ? _selected : 'calm_female',
                decoration: InputDecoration(
                  isDense: true,
                  filled: true,
                  fillColor: Colors.white.withValues(alpha: 0.62),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(18),
                    borderSide: BorderSide(
                      color: Colors.white.withValues(alpha: 0.8),
                    ),
                  ),
                  enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(18),
                    borderSide: BorderSide(
                      color: Colors.white.withValues(alpha: 0.8),
                    ),
                  ),
                ),
                items: _voices
                    .map(
                      (voice) => DropdownMenuItem(
                        value: voice['id'].toString(),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text(voice['name']?.toString() ?? 'Voice'),
                            Text(
                              voice['style']?.toString() ?? '',
                              style: const TextStyle(
                                fontSize: 11,
                                color: Color(0xFF6B6F7B),
                              ),
                            ),
                          ],
                        ),
                      ),
                    )
                    .toList(),
                selectedItemBuilder: (context) => _voices
                    .map(
                      (voice) => Align(
                        alignment: Alignment.centerLeft,
                        child: Text(
                          voice['name']?.toString() ?? 'Voice',
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    )
                    .toList(),
                onChanged: _loading || _saving
                    ? null
                    : (value) {
                        if (value != null) {
                          _save(value);
                        }
                      },
              ),
            ),
            const SizedBox(width: 10),
            IconButton.filledTonal(
              onPressed: _loading || _saving || _previewing ? null : _preview,
              icon: _previewing
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.play_arrow_rounded),
              tooltip: 'Preview voice',
            ),
          ],
        ),
      );
    }

    final selectedVoice = _selectedVoice;
    final fallbackNote = selectedVoice['fallback_note']?.toString() ?? '';
    final distinct = selectedVoice['is_distinct_voice_supported'] == true;
    final providerLabel = distinct
        ? 'Distinct provider voice'
        : (fallbackNote.isNotEmpty ? fallbackNote : 'Local fallback voice');
    Widget controlsWithNote({double? width}) {
      return SizedBox(
        width: width,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            controls(),
            const SizedBox(height: 8),
            Text(
              providerLabel,
              style: const TextStyle(
                fontSize: 11,
                height: 1.35,
                color: Color(0xFF6B6F7B),
              ),
            ),
          ],
        ),
      );
    }

    const label = Expanded(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'AiPal voice',
            style: TextStyle(
              fontFamily: 'Manrope',
              fontSize: 18,
              fontWeight: FontWeight.w800,
              color: Color(0xFF1B1C1A),
            ),
          ),
          SizedBox(height: 5),
          Text(
            'Choose the spoken voice used for greetings and replies.',
            style: TextStyle(
              fontSize: 13,
              height: 1.4,
              color: Color(0xFF575C6B),
            ),
          ),
        ],
      ),
    );

    return LayoutBuilder(
      builder: (context, constraints) {
        if (constraints.maxWidth < 620) {
          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Row(
                children: [
                  _RoundIcon(
                    icon: Icons.spatial_audio_off_rounded,
                    background: Color(0xFFE8F3F1),
                  ),
                  SizedBox(width: 24),
                  label,
                ],
              ),
              const SizedBox(height: 16),
              controlsWithNote(),
            ],
          );
        }

        return Row(
          children: [
            const _RoundIcon(
              icon: Icons.spatial_audio_off_rounded,
              background: Color(0xFFE8F3F1),
            ),
            const SizedBox(width: 24),
            label,
            const SizedBox(width: 20),
            controlsWithNote(width: 250),
          ],
        );
      },
    );
  }
}

class _PremiumSwitch extends StatelessWidget {
  const _PremiumSwitch({
    required this.value,
    required this.onChanged,
    this.enabled = true,
  });

  final bool value;
  final bool enabled;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: enabled ? () => onChanged(!value) : null,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 260),
        width: 52,
        height: 28,
        padding: const EdgeInsets.all(3),
        decoration: BoxDecoration(
          color: value ? const Color(0xFFFFC815) : const Color(0xFFDBDAD6),
          borderRadius: BorderRadius.circular(999),
        ),
        child: AnimatedAlign(
          duration: const Duration(milliseconds: 260),
          alignment: value ? Alignment.centerRight : Alignment.centerLeft,
          curve: Curves.easeOutCubic,
          child: Container(
            width: 22,
            height: 22,
            decoration: const BoxDecoration(
              shape: BoxShape.circle,
              color: Colors.white,
            ),
          ),
        ),
      ),
    );
  }
}

class _ConnectivityCard extends StatelessWidget {
  const _ConnectivityCard({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.action,
    required this.onTap,
    this.badge,
    this.iconColor,
    this.darkAction = false,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final String action;
  final VoidCallback onTap;
  final String? badge;
  final Color? iconColor;
  final bool darkAction;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(48),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 40, sigmaY: 40),
        child: Material(
          color: Colors.white.withValues(alpha: 0.40),
          borderRadius: BorderRadius.circular(48),
          child: InkWell(
            onTap: onTap,
            borderRadius: BorderRadius.circular(48),
            child: Container(
              padding: const EdgeInsets.all(24),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(48),
                border: Border.all(color: Colors.white.withValues(alpha: 0.80)),
                boxShadow: [
                  BoxShadow(
                    color: const Color(0xFF1A1F2C).withValues(alpha: 0.04),
                    blurRadius: 60,
                    offset: const Offset(0, 30),
                  ),
                ],
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Icon(
                        icon,
                        size: 34,
                        color: iconColor ?? const Color(0xFFFFC815),
                      ),
                      const Spacer(),
                      if (badge != null)
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 9,
                            vertical: 4,
                          ),
                          decoration: BoxDecoration(
                            color: const Color(0xFFFFF2B8),
                            borderRadius: BorderRadius.circular(999),
                          ),
                          child: Text(
                            badge!,
                            style: const TextStyle(
                              fontSize: 10,
                              fontWeight: FontWeight.w900,
                              letterSpacing: 0.9,
                              color: Color(0xFF583B6B),
                            ),
                          ),
                        ),
                    ],
                  ),
                  const SizedBox(height: 20),
                  Text(
                    title,
                    style: const TextStyle(
                      fontFamily: 'Manrope',
                      fontSize: 18,
                      fontWeight: FontWeight.w800,
                      color: Color(0xFF1B1C1A),
                    ),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    subtitle,
                    style: const TextStyle(
                      fontSize: 13,
                      height: 1.45,
                      color: Color(0xFF575C6B),
                    ),
                  ),
                  const SizedBox(height: 22),
                  if (darkAction)
                    SizedBox(
                      width: double.infinity,
                      child: FilledButton(
                        onPressed: onTap,
                        style: FilledButton.styleFrom(
                          backgroundColor: const Color(0xFF2F312E),
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(vertical: 15),
                          shape: const StadiumBorder(),
                        ),
                        child: Text(action),
                      ),
                    )
                  else
                    Row(
                      children: [
                        Text(
                          action,
                          style: const TextStyle(
                            fontWeight: FontWeight.w800,
                            color: Color(0xFFFFC815),
                          ),
                        ),
                        const SizedBox(width: 6),
                        const Icon(
                          Icons.arrow_forward_rounded,
                          size: 17,
                          color: Color(0xFFFFC815),
                        ),
                      ],
                    ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _SettingsFooter extends StatelessWidget {
  const _SettingsFooter();

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<PackageInfo>(
      future: PackageInfo.fromPlatform(),
      builder: (context, snapshot) {
        final info = snapshot.data;

        return Column(
          children: [
            const Divider(color: Color(0x33E8DFAF)),
            const SizedBox(height: 34),
            const Text(
              'AiPal Intelligence Shell',
              style: TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w900,
                letterSpacing: 2.4,
                color: Color(0xFF575C6B),
              ),
            ),
            const SizedBox(height: 8),
            Text(
              info != null
                  ? 'Version ${info.version} (Build ${info.buildNumber})'
                  : 'Loading version…',
              style: const TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w700,
                color: Color(0xFF4B444D),
              ),
            ),
            const SizedBox(height: 20),
            Container(
              constraints: const BoxConstraints(maxWidth: 520),
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
              decoration: BoxDecoration(
                color: const Color(0xFFF4F4F0).withValues(alpha: 0.58),
                borderRadius: BorderRadius.circular(32),
              ),
              child: const Text(
                'AiPal is a supportive companion, not medical advice. Please consult with a healthcare professional for clinical needs.',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 12.5,
                  height: 1.45,
                  color: Color(0xFF575C6B),
                ),
              ),
            ),
          ],
        );
      },
    );
  }
}

class _AccountActionCard extends StatelessWidget {
  const _AccountActionCard({
    required this.title,
    required this.subtitle,
    required this.action,
    required this.onTap,
  });

  final String title;
  final String subtitle;
  final String action;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(32),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 40, sigmaY: 40),
        child: Material(
          color: Colors.white.withValues(alpha: 0.42),
          borderRadius: BorderRadius.circular(32),
          child: InkWell(
            onTap: onTap,
            borderRadius: BorderRadius.circular(32),
            child: Container(
              width: double.infinity,
              constraints: const BoxConstraints(maxWidth: 520),
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(32),
                border: Border.all(color: Colors.white.withValues(alpha: 0.8)),
                boxShadow: [
                  BoxShadow(
                    color: const Color(0xFF1A1F2C).withValues(alpha: 0.04),
                    blurRadius: 60,
                    offset: const Offset(0, 30),
                  ),
                ],
              ),
              child: Row(
                children: [
                  Container(
                    width: 48,
                    height: 48,
                    decoration: BoxDecoration(
                      color: const Color(0xFFFFF1F0),
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: const Icon(
                      Icons.logout_rounded,
                      color: Color(0xFFBA1A1A),
                    ),
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          title,
                          style: const TextStyle(
                            fontFamily: 'Manrope',
                            fontSize: 18,
                            fontWeight: FontWeight.w800,
                            color: Color(0xFF1B1C1A),
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          subtitle,
                          style: const TextStyle(
                            fontSize: 13,
                            height: 1.45,
                            color: Color(0xFF575C6B),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(width: 12),
                  Text(
                    action,
                    style: const TextStyle(
                      fontWeight: FontWeight.w800,
                      color: Color(0xFFBA1A1A),
                    ),
                  ),
                  const SizedBox(width: 4),
                  const Icon(
                    Icons.arrow_forward_rounded,
                    size: 17,
                    color: Color(0xFFBA1A1A),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _RoundIcon extends StatelessWidget {
  const _RoundIcon({required this.icon, required this.background});

  final IconData icon;
  final Color background;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 52,
      height: 52,
      decoration: BoxDecoration(shape: BoxShape.circle, color: background),
      child: Icon(icon, color: const Color(0xFFFFC815), size: 28),
    );
  }
}

class _SoftDivider extends StatelessWidget {
  const _SoftDivider();

  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.symmetric(vertical: 20),
      child: Divider(height: 1, color: Color(0x33E8DFAF)),
    );
  }
}

class _SettingsAtmosphere extends StatelessWidget {
  const _SettingsAtmosphere();

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        Container(color: const Color(0xFFFAF9F5)),
        Positioned(
          top: -180,
          right: -120,
          child: _Blob(color: const Color(0xFFFFC815).withValues(alpha: 0.08)),
        ),
        Positioned(
          bottom: -180,
          left: 180,
          child: _Blob(color: const Color(0xFF003B2B).withValues(alpha: 0.08)),
        ),
      ],
    );
  }
}

class _Blob extends StatelessWidget {
  const _Blob({required this.color});

  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 560,
      height: 560,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        boxShadow: [BoxShadow(color: color, blurRadius: 140, spreadRadius: 90)],
      ),
    );
  }
}
