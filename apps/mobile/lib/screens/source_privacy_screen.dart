import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/app_state.dart';
import 'home_shell.dart';

const _brandGreen = Color(0xFF003B2B);

class SourcePrivacyScreen extends StatefulWidget {
  const SourcePrivacyScreen({super.key});

  @override
  State<SourcePrivacyScreen> createState() => _SourcePrivacyScreenState();
}

class _SourcePrivacyScreenState extends State<SourcePrivacyScreen> {
  Future<Map<String, dynamic>>? _future;
  bool _deleteBusy = false;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<Map<String, dynamic>> _load() async {
    final api = context.read<AppState>().api;
    final accounts = await api.listConnectedAccounts();
    return {'accounts': accounts};
  }

  Future<void> _deleteAll() async {
    setState(() => _deleteBusy = true);
    try {
      await context.read<AppState>().api.deleteConnectedData();
      if (!mounted) return;
      setState(() => _future = _load());
    } finally {
      if (mounted) setState(() => _deleteBusy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AiPalShellScaffold(
      title: 'Source Privacy',
      subtitle: 'See connected accounts and control imported data',
      showDesktopSidebar: false,
      showMobileBottomNav: false,
      onNotificationsTap: () {},
      onProfileTap: () {},
      body: FutureBuilder<Map<String, dynamic>>(
        future: _future,
        builder: (context, snapshot) {
          final accounts =
              (snapshot.data?['accounts'] as List<dynamic>? ?? const []);
          return ListView(
            padding: const EdgeInsets.fromLTRB(20, 24, 20, 96),
            children: [
              _GlassPanel(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Source privacy',
                      style: TextStyle(
                        fontSize: 28,
                        fontWeight: FontWeight.w800,
                        color: _brandGreen,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text('Connected accounts: ${accounts.length}'),
                    const SizedBox(height: 12),
                    Align(
                      alignment: Alignment.centerRight,
                      child: FilledButton(
                        onPressed: _deleteBusy ? null : _deleteAll,
                        child: Text(
                          _deleteBusy ? 'Deleting...' : 'Delete imported data',
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),
              _GlassPanel(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Accounts',
                      style: TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w700,
                        color: _brandGreen,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      accounts.isEmpty
                          ? 'No accounts connected.'
                          : accounts
                                .map((a) => a['provider'].toString())
                                .join('\n'),
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
