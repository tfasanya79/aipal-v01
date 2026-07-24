import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/app_state.dart';
import 'home_shell.dart';

const _brandGreen = Color(0xFF003B2B);

class ConnectedSourcesScreen extends StatefulWidget {
  const ConnectedSourcesScreen({super.key});

  @override
  State<ConnectedSourcesScreen> createState() => _ConnectedSourcesScreenState();
}

class _ConnectedSourcesScreenState extends State<ConnectedSourcesScreen> {
  Future<Map<String, dynamic>>? _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<Map<String, dynamic>> _load() async {
    final api = context.read<AppState>().api;
    final results = await Future.wait([
      api.listConnectedAccounts(),
      api.listConnectedItems(),
      api.listEmailItems(),
    ]);
    return {
      'accounts': results[0],
      'items': results[1],
      'emailItems': results[2],
    };
  }

  @override
  Widget build(BuildContext context) {
    return AiPalShellScaffold(
      title: 'Connected Sources',
      subtitle:
          'Email, calendar, documents, and other private source connections',
      showDesktopSidebar: false,
      showMobileBottomNav: false,
      onNotificationsTap: () {},
      onProfileTap: () {},
      body: FutureBuilder<Map<String, dynamic>>(
        future: _future,
        builder: (context, snapshot) {
          final accounts =
              (snapshot.data?['accounts'] as List<dynamic>? ?? const []);
          final items = (snapshot.data?['items'] as List<dynamic>? ?? const []);
          return ListView(
            padding: const EdgeInsets.fromLTRB(20, 24, 20, 96),
            children: [
              _GlassPanel(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Connected sources',
                      style: TextStyle(
                        fontSize: 28,
                        fontWeight: FontWeight.w800,
                        color: _brandGreen,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'Accounts: ${accounts.length} · Items: ${items.length}',
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
                          ? 'No connected accounts yet.'
                          : accounts
                                .map(
                                  (a) =>
                                      '${a['provider']} · ${a['account_label']}',
                                )
                                .join('\n'),
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
                      'Items',
                      style: TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w700,
                        color: _brandGreen,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      items.isEmpty
                          ? 'No connected items yet.'
                          : items
                                .take(8)
                                .map((i) => i['title'].toString())
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
