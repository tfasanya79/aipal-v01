import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/app_state.dart';
import 'home_shell.dart';

const _brandGreen = Color(0xFF003B2B);

class BusinessContextScreen extends StatefulWidget {
  const BusinessContextScreen({super.key});

  @override
  State<BusinessContextScreen> createState() => _BusinessContextScreenState();
}

class _BusinessContextScreenState extends State<BusinessContextScreen> {
  Future<Map<String, dynamic>>? _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<Map<String, dynamic>> _load() async {
    final api = context.read<AppState>().api;
    final projects = await api.listBusinessProjects();
    final events = projects.isEmpty
        ? <dynamic>[]
        : await api.getBusinessProjectEvents(projects.first['id'].toString());
    return {'projects': projects, 'events': events};
  }

  @override
  Widget build(BuildContext context) {
    return AiPalShellScaffold(
      title: 'Business Context',
      subtitle: 'Projects, goals, risks, opportunities, and events',
      showDesktopSidebar: false,
      showMobileBottomNav: false,
      onNotificationsTap: () {},
      onProfileTap: () {},
      body: FutureBuilder<Map<String, dynamic>>(
        future: _future,
        builder: (context, snapshot) {
          final projects =
              (snapshot.data?['projects'] as List<dynamic>? ?? const []);
          final events =
              (snapshot.data?['events'] as List<dynamic>? ?? const []);
          return ListView(
            padding: const EdgeInsets.fromLTRB(20, 24, 20, 96),
            children: [
              _GlassPanel(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Business context',
                      style: TextStyle(
                        fontSize: 28,
                        fontWeight: FontWeight.w800,
                        color: _brandGreen,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text('Projects: ${projects.length}'),
                  ],
                ),
              ),
              const SizedBox(height: 16),
              _GlassPanel(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Projects',
                      style: TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w700,
                        color: _brandGreen,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      projects.isEmpty
                          ? 'No projects yet.'
                          : projects
                                .map((p) => p['name'].toString())
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
                      'Events',
                      style: TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w700,
                        color: _brandGreen,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      events.isEmpty
                          ? 'No events yet.'
                          : events.map((e) => e['title'].toString()).join('\n'),
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
