import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/app_state.dart';
import 'goal_reflection_detail_screens.dart';

class ReflectionScreen extends StatefulWidget {
  const ReflectionScreen({super.key});

  @override
  State<ReflectionScreen> createState() => _ReflectionScreenState();
}

class _ReflectionScreenState extends State<ReflectionScreen> {
  Future<List<dynamic>>? _reflectionsFuture;

  @override
  void initState() {
    super.initState();
    _reflectionsFuture = _load();
  }

  Future<List<dynamic>> _load() =>
      context.read<AppState>().api.listReflections();

  Future<void> _refresh() async {
    if (!mounted) return;
    setState(() {
      _reflectionsFuture = _load();
    });
  }

  Future<void> _editReflection([
    Map<String, dynamic>? reflection,
    String? forcedType,
  ]) async {
    final api = context.read<AppState>().api;
    final winsController = TextEditingController(
      text: reflection?['wins']?.toString() ?? '',
    );
    final challengesController = TextEditingController(
      text: reflection?['challenges']?.toString() ?? '',
    );
    final lessonsController = TextEditingController(
      text: reflection?['lessons']?.toString() ?? '',
    );
    final moodController = TextEditingController(
      text: reflection?['mood']?.toString() ?? '',
    );
    var type = forcedType ?? reflection?['type']?.toString() ?? 'daily';

    final result = await showModalBottomSheet<Map<String, dynamic>>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => StatefulBuilder(
        builder: (context, setSheetState) => _ReflectionEditorSheet(
          winsController: winsController,
          challengesController: challengesController,
          lessonsController: lessonsController,
          moodController: moodController,
          type: type,
          onTypeChanged: (v) => setSheetState(() => type = v),
        ),
      ),
    );

    winsController.dispose();
    challengesController.dispose();
    lessonsController.dispose();
    moodController.dispose();

    if (result == null) return;
    if (reflection == null) {
      await api.createReflection(result);
    } else {
      await api.updateReflection(reflection['id'].toString(), result);
    }
    await _refresh();
  }

  Future<void> _deleteReflection(String id) async {
    final api = context.read<AppState>().api;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete reflection?'),
        content: const Text('This removes the reflection permanently.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (ok != true) return;
    await api.deleteReflection(id);
    await _refresh();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFFAF9F5),
      floatingActionButton: FloatingActionButton(
        onPressed: () => _editReflection(null, 'daily'),
        backgroundColor: const Color(0xFFFFC815),
        foregroundColor: Colors.white,
        child: const Icon(Icons.edit_note_rounded),
      ),
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 12, 20, 18),
              child: Row(
                children: [
                  _HeaderButton(
                    icon: Icons.arrow_back_rounded,
                    onTap: () => Navigator.pop(context),
                  ),
                  const SizedBox(width: 14),
                  const Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Reflections',
                          style: TextStyle(
                            fontFamily: 'Manrope',
                            fontSize: 28,
                            fontWeight: FontWeight.w800,
                            color: Color(0xFF1B1C1A),
                          ),
                        ),
                        SizedBox(height: 2),
                        Text(
                          'Capture wins, challenges, lessons, and mood',
                          style: TextStyle(
                            fontSize: 13,
                            color: Color(0xFF575C6B),
                          ),
                        ),
                      ],
                    ),
                  ),
                  TextButton(
                    onPressed: () => _editReflection(null, 'daily'),
                    child: const Text('Daily'),
                  ),
                  TextButton(
                    onPressed: () => _editReflection(null, 'weekly'),
                    child: const Text('Weekly'),
                  ),
                ],
              ),
            ),
            Expanded(
              child: RefreshIndicator(
                onRefresh: _refresh,
                child: FutureBuilder<List<dynamic>>(
                  future: _reflectionsFuture,
                  builder: (context, snapshot) {
                    final reflections = snapshot.data ?? const [];
                    if (snapshot.connectionState == ConnectionState.waiting) {
                      return const Center(child: CircularProgressIndicator());
                    }
                    return ListView(
                      padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
                      children: [
                        if (reflections.isEmpty)
                          const _EmptyState()
                        else
                          ...reflections.map(
                            (reflection) => _ReflectionCard(
                              reflection: reflection.cast<String, dynamic>(),
                              onOpen: () => Navigator.of(context).push(
                                MaterialPageRoute(
                                  builder: (_) => ReflectionDetailScreen(
                                    reflectionId: reflection['id'].toString(),
                                  ),
                                ),
                              ),
                              onEdit: () => _editReflection(
                                reflection.cast<String, dynamic>(),
                              ),
                              onDelete: () => _deleteReflection(
                                reflection['id'].toString(),
                              ),
                            ),
                          ),
                      ],
                    );
                  },
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ReflectionCard extends StatelessWidget {
  const _ReflectionCard({
    required this.reflection,
    required this.onOpen,
    required this.onEdit,
    required this.onDelete,
  });
  final Map<String, dynamic> reflection;
  final VoidCallback onOpen;
  final VoidCallback onEdit;
  final VoidCallback onDelete;
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Material(
        color: Colors.white.withValues(alpha: 0.7),
        borderRadius: BorderRadius.circular(26),
        child: InkWell(
          borderRadius: BorderRadius.circular(26),
          onTap: onOpen,
          child: Padding(
            padding: const EdgeInsets.all(18),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        '${reflection['type']?.toString().toUpperCase() ?? 'DAILY'} REFLECTION',
                        style: const TextStyle(
                          fontFamily: 'Manrope',
                          fontSize: 16,
                          fontWeight: FontWeight.w800,
                          color: Color(0xFF1B1C1A),
                        ),
                      ),
                    ),
                    _Chip(label: reflection['mood']?.toString() ?? 'neutral'),
                  ],
                ),
                const SizedBox(height: 10),
                if ((reflection['wins']?.toString() ?? '').isNotEmpty)
                  _Block(label: 'Wins', value: reflection['wins'].toString()),
                if ((reflection['challenges']?.toString() ?? '').isNotEmpty)
                  _Block(
                    label: 'Challenges',
                    value: reflection['challenges'].toString(),
                  ),
                if ((reflection['lessons']?.toString() ?? '').isNotEmpty)
                  _Block(
                    label: 'Lessons',
                    value: reflection['lessons'].toString(),
                  ),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 8,
                  children: [
                    OutlinedButton(
                      onPressed: onEdit,
                      child: const Text('Edit'),
                    ),
                    FilledButton.tonal(
                      onPressed: onDelete,
                      child: const Text('Delete'),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _ReflectionEditorSheet extends StatelessWidget {
  const _ReflectionEditorSheet({
    required this.winsController,
    required this.challengesController,
    required this.lessonsController,
    required this.moodController,
    required this.type,
    required this.onTypeChanged,
  });

  final TextEditingController winsController;
  final TextEditingController challengesController;
  final TextEditingController lessonsController;
  final TextEditingController moodController;
  final String type;
  final ValueChanged<String> onTypeChanged;

  @override
  Widget build(BuildContext context) {
    var localType = type;
    return Padding(
      padding: EdgeInsets.only(
        bottom: MediaQuery.of(context).viewInsets.bottom + 16,
        left: 16,
        right: 16,
      ),
      child: Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: const Color(0xFFFAF9F5),
          borderRadius: BorderRadius.circular(30),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const _SheetHandle(),
            const SizedBox(height: 18),
            DropdownButtonFormField<String>(
              initialValue: localType,
              items: const [
                DropdownMenuItem(value: 'daily', child: Text('daily')),
                DropdownMenuItem(value: 'weekly', child: Text('weekly')),
              ],
              onChanged: (v) {
                final next = v ?? 'daily';
                localType = next;
                onTypeChanged(next);
              },
              decoration: const InputDecoration(labelText: 'Type'),
            ),
            const SizedBox(height: 12),
            _Field(controller: winsController, label: 'Wins', maxLines: 3),
            const SizedBox(height: 12),
            _Field(
              controller: challengesController,
              label: 'Challenges',
              maxLines: 3,
            ),
            const SizedBox(height: 12),
            _Field(
              controller: lessonsController,
              label: 'Lessons',
              maxLines: 3,
            ),
            const SizedBox(height: 12),
            _Field(controller: moodController, label: 'Mood'),
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                onPressed: () {
                  Navigator.pop(context, {
                    'type': localType,
                    'wins': winsController.text.trim(),
                    'challenges': challengesController.text.trim(),
                    'lessons': lessonsController.text.trim(),
                    'mood': moodController.text.trim(),
                  });
                },
                child: const Text('Save Reflection'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Field extends StatelessWidget {
  const _Field({
    required this.controller,
    required this.label,
    this.maxLines = 1,
  });
  final TextEditingController controller;
  final String label;
  final int maxLines;
  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: controller,
      maxLines: maxLines,
      decoration: InputDecoration(labelText: label),
    );
  }
}

class _Block extends StatelessWidget {
  const _Block({required this.label, required this.value});
  final String label;
  final String value;
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: const TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w800,
              color: Color(0xFFFFC815),
            ),
          ),
          const SizedBox(height: 3),
          Text(
            value,
            style: const TextStyle(
              fontSize: 13.5,
              height: 1.5,
              color: Color(0xFF4B444D),
            ),
          ),
        ],
      ),
    );
  }
}

class _Chip extends StatelessWidget {
  const _Chip({required this.label});
  final String label;
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: const Color(0xFFF4F1EB),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        label,
        style: const TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w800,
          color: Color(0xFF1B1C1A),
        ),
      ),
    );
  }
}

class _HeaderButton extends StatelessWidget {
  const _HeaderButton({required this.icon, required this.onTap});
  final IconData icon;
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) {
    return Container(
      width: 48,
      height: 48,
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.75),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFFE6E1D6)),
      ),
      child: IconButton(
        icon: Icon(icon, color: const Color(0xFF1B1C1A)),
        onPressed: onTap,
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState();
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.6),
        borderRadius: BorderRadius.circular(24),
      ),
      child: const Text(
        'No reflections yet. Daily or weekly reviews will appear here.',
        style: TextStyle(fontSize: 14, height: 1.5, color: Color(0xFF4B444D)),
      ),
    );
  }
}

class _SheetHandle extends StatelessWidget {
  const _SheetHandle();
  @override
  Widget build(BuildContext context) {
    return Container(
      width: 48,
      height: 5,
      decoration: BoxDecoration(
        color: const Color(0xFFE8DFAF),
        borderRadius: BorderRadius.circular(999),
      ),
    );
  }
}
