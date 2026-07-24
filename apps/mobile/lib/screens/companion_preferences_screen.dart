import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/app_state.dart';
import 'home_shell.dart';

const _brandGreen = Color(0xFF003B2B);
const _teal = Color(0xFF003B2B);

class CompanionPreferencesScreen extends StatefulWidget {
  const CompanionPreferencesScreen({super.key});

  @override
  State<CompanionPreferencesScreen> createState() =>
      _CompanionPreferencesScreenState();
}

class _CompanionPreferencesScreenState
    extends State<CompanionPreferencesScreen> {
  Future<Map<String, dynamic>>? _future;
  final _quietStart = TextEditingController();
  final _quietEnd = TextEditingController();
  final _humor = TextEditingController(text: '1');
  final _directness = TextEditingController(text: '5');
  final _tone = ['warm', 'calm', 'direct', 'playful', 'professional'];
  final _lengths = ['short', 'balanced', 'detailed'];
  final _paces = ['slow', 'normal', 'energetic'];
  bool _proactive = true;
  String _selectedTone = 'warm';
  String _selectedLength = 'balanced';
  String _selectedPace = 'normal';

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  @override
  void dispose() {
    _quietStart.dispose();
    _quietEnd.dispose();
    _humor.dispose();
    _directness.dispose();
    super.dispose();
  }

  Future<Map<String, dynamic>> _load() async {
    final prefs = await context.read<AppState>().api.getCompanionPreferences();
    _proactive = prefs['proactive_enabled'] ?? true;
    _quietStart.text = prefs['quiet_hours_start']?.toString() ?? '';
    _quietEnd.text = prefs['quiet_hours_end']?.toString() ?? '';
    _humor.text = '${prefs['humor_level'] ?? 1}';
    _directness.text = '${prefs['directness_level'] ?? 5}';
    _selectedTone = prefs['tone']?.toString() ?? 'warm';
    _selectedLength = prefs['response_length']?.toString() ?? 'balanced';
    _selectedPace = prefs['voice_pace']?.toString() ?? 'normal';
    return prefs;
  }

  Future<void> _save() async {
    await context.read<AppState>().api.updateCompanionPreferences({
      'proactive_enabled': _proactive,
      'quiet_hours_start': _quietStart.text.trim().isEmpty
          ? null
          : _quietStart.text.trim(),
      'quiet_hours_end': _quietEnd.text.trim().isEmpty
          ? null
          : _quietEnd.text.trim(),
      'humor_level': int.tryParse(_humor.text.trim()) ?? 1,
      'directness_level': int.tryParse(_directness.text.trim()) ?? 5,
      'tone': _selectedTone,
      'response_length': _selectedLength,
      'voice_pace': _selectedPace,
    });
    if (!mounted) return;
    setState(() => _future = _load());
  }

  @override
  Widget build(BuildContext context) {
    return AiPalShellScaffold(
      title: 'Companion Preferences',
      subtitle: 'Tune how AiPal speaks and when it should gently check in',
      showDesktopSidebar: false,
      showMobileBottomNav: false,
      onNotificationsTap: () {},
      onProfileTap: () {},
      body: FutureBuilder<Map<String, dynamic>>(
        future: _future,
        builder: (context, snapshot) {
          return ListView(
            padding: const EdgeInsets.fromLTRB(20, 24, 20, 96),
            children: [
              _GlassPanel(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Companion preferences',
                      style: TextStyle(
                        fontSize: 28,
                        fontWeight: FontWeight.w800,
                        color: _brandGreen,
                      ),
                    ),
                    const SizedBox(height: 8),
                    const Text(
                      'Tune how AiPal feels and how often it should nudge you.',
                    ),
                    const SizedBox(height: 16),
                    SwitchListTile(
                      contentPadding: EdgeInsets.zero,
                      value: _proactive,
                      onChanged: (value) => setState(() => _proactive = value),
                      title: const Text('Proactive check-ins'),
                      subtitle: const Text(
                        'Let AiPal nudge you gently when it feels useful.',
                      ),
                    ),
                    TextField(
                      controller: _quietStart,
                      decoration: const InputDecoration(
                        labelText: 'Quiet hours start (HH:MM)',
                      ),
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      controller: _quietEnd,
                      decoration: const InputDecoration(
                        labelText: 'Quiet hours end (HH:MM)',
                      ),
                    ),
                    const SizedBox(height: 12),
                    DropdownButtonFormField<String>(
                      initialValue: _selectedTone,
                      items: _tone
                          .map(
                            (tone) => DropdownMenuItem(
                              value: tone,
                              child: Text(tone),
                            ),
                          )
                          .toList(),
                      onChanged: (value) =>
                          setState(() => _selectedTone = value ?? 'warm'),
                      decoration: const InputDecoration(labelText: 'Tone'),
                    ),
                    const SizedBox(height: 12),
                    DropdownButtonFormField<String>(
                      initialValue: _selectedLength,
                      items: _lengths
                          .map(
                            (v) => DropdownMenuItem(value: v, child: Text(v)),
                          )
                          .toList(),
                      onChanged: (value) =>
                          setState(() => _selectedLength = value ?? 'balanced'),
                      decoration: const InputDecoration(
                        labelText: 'Response length',
                      ),
                    ),
                    const SizedBox(height: 12),
                    DropdownButtonFormField<String>(
                      initialValue: _selectedPace,
                      items: _paces
                          .map(
                            (v) => DropdownMenuItem(value: v, child: Text(v)),
                          )
                          .toList(),
                      onChanged: (value) =>
                          setState(() => _selectedPace = value ?? 'normal'),
                      decoration: const InputDecoration(
                        labelText: 'Voice pace',
                      ),
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      controller: _humor,
                      decoration: const InputDecoration(
                        labelText: 'Humor level (0-5)',
                      ),
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      controller: _directness,
                      decoration: const InputDecoration(
                        labelText: 'Directness (1-10)',
                      ),
                    ),
                    const SizedBox(height: 18),
                    Align(
                      alignment: Alignment.centerRight,
                      child: FilledButton(
                        style: FilledButton.styleFrom(
                          backgroundColor: _teal,
                          foregroundColor: Colors.white,
                        ),
                        onPressed: _save,
                        child: const Text('Save preferences'),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _GlassPanel extends StatelessWidget {
  const _GlassPanel({required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(18),
    decoration: BoxDecoration(
      color: Colors.white.withValues(alpha: 0.72),
      borderRadius: BorderRadius.circular(24),
      border: Border.all(color: Colors.white.withValues(alpha: 0.75)),
    ),
    child: child,
  );
}
