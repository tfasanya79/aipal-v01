import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/app_state.dart';
import '../services/memory_export.dart';
import 'memory_timeline_screen.dart';

class MemoryControlCenterScreen extends StatefulWidget {
  const MemoryControlCenterScreen({super.key});

  @override
  State<MemoryControlCenterScreen> createState() =>
      _MemoryControlCenterScreenState();
}

class _MemoryControlCenterScreenState extends State<MemoryControlCenterScreen> {
  Future<List<dynamic>>? _memoriesFuture;
  Future<List<dynamic>>? _pendingFuture;

  @override
  void initState() {
    super.initState();
    _memoriesFuture = _loadMemories();
    _pendingFuture = _loadPendingMemories();
  }

  Future<List<dynamic>> _loadMemories() =>
      context.read<AppState>().api.listMemories();

  Future<List<dynamic>> _loadPendingMemories() =>
      context.read<AppState>().api.listPendingMemories();

  Future<void> _refresh() async {
    if (!mounted) return;
    setState(() {
      _memoriesFuture = _loadMemories();
      _pendingFuture = _loadPendingMemories();
    });
  }

  Future<void> _exportMemories() async {
    final api = context.read<AppState>().api;
    final data = await api.exportMemories();
    if (!mounted) return;
    final filename =
        'aipal-memories-${DateTime.now().toIso8601String().split('T').first}.json';
    final jsonText = const JsonEncoder.withIndent('  ').convert(data);
    final savedPath = await saveJsonFile(filename, jsonText);
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          savedPath == null
              ? 'Exported ${data.length} memories'
              : 'Saved ${data.length} memories to $savedPath',
        ),
      ),
    );
  }

  Future<void> _clearHistory() async {
    final api = context.read<AppState>().api;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Clear conversation history?'),
        content: const Text(
          'This removes the saved chat history for the account.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Clear'),
          ),
        ],
      ),
    );
    if (ok != true) return;
    await api.clearConversationHistory();
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Conversation history cleared')),
    );
    await _refresh();
  }

  Future<void> _editMemory([Map<String, dynamic>? memory]) async {
    final api = context.read<AppState>().api;
    final titleController = TextEditingController(
      text: memory?['title']?.toString() ?? '',
    );
    final contentController = TextEditingController(
      text: memory?['content']?.toString() ?? '',
    );
    final typeController = TextEditingController(
      text: memory?['type']?.toString() ?? 'fact',
    );
    final lifeAreaController = TextEditingController(
      text: memory?['life_area']?.toString() ?? '',
    );
    final importanceController = TextEditingController(
      text: memory?['importance']?.toString() ?? '1',
    );
    final confidenceController = TextEditingController(
      text: memory?['confidence']?.toString() ?? '0.5',
    );
    final expiresAtController = TextEditingController(
      text: memory?['expires_at']?.toString() ?? '',
    );
    final reasonController = TextEditingController(
      text: memory?['suggested_reason']?.toString() ?? '',
    );
    var memoryScope = memory?['memory_scope']?.toString() ?? 'permanent';
    var approvalStatus = memory?['approval_status']?.toString() ?? 'approved';
    var sensitive = memory?['sensitive'] as bool? ?? false;
    var approved = memory?['user_approved'] as bool? ?? true;
    var paused = memory?['paused'] as bool? ?? false;

    final result = await showModalBottomSheet<Map<String, dynamic>>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => StatefulBuilder(
        builder: (context, setSheetState) => _MemoryEditorSheet(
          titleController: titleController,
          contentController: contentController,
          typeController: typeController,
          lifeAreaController: lifeAreaController,
          importanceController: importanceController,
          confidenceController: confidenceController,
          expiresAtController: expiresAtController,
          reasonController: reasonController,
          memoryScope: memoryScope,
          approvalStatus: approvalStatus,
          sensitive: sensitive,
          approved: approved,
          paused: paused,
          onMemoryScopeChanged: (v) => setSheetState(() => memoryScope = v),
          onApprovalStatusChanged: (v) =>
              setSheetState(() => approvalStatus = v),
          onSensitiveChanged: (v) => setSheetState(() => sensitive = v),
          onApprovedChanged: (v) => setSheetState(() => approved = v),
          onPausedChanged: (v) => setSheetState(() => paused = v),
        ),
      ),
    );

    titleController.dispose();
    contentController.dispose();
    typeController.dispose();
    lifeAreaController.dispose();
    importanceController.dispose();
    confidenceController.dispose();
    expiresAtController.dispose();
    reasonController.dispose();

    if (result == null) return;
    result['memory_scope'] = memoryScope;
    result['approval_status'] = approvalStatus;
    result['user_approved'] = approvalStatus == 'approved';
    if (memory == null) {
      await api.createMemory(result);
    } else {
      await api.editMemory(memory['id'].toString(), result);
    }
    await _refresh();
  }

  Future<void> _deleteMemory(String id) async {
    final api = context.read<AppState>().api;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete memory?'),
        content: const Text('This removes the saved memory permanently.'),
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
    await api.deleteMemory(id);
    await _refresh();
  }

  Future<void> _togglePause(Map<String, dynamic> memory) async {
    final api = context.read<AppState>().api;
    await api.pauseMemory(
      memory['id'].toString(),
      paused: !(memory['paused'] as bool? ?? false),
    );
    await _refresh();
  }

  Future<void> _approveMemory(String id) async {
    final api = context.read<AppState>().api;
    await api.approveMemory(id);
    await _refresh();
  }

  Future<void> _rejectMemory(String id) async {
    final api = context.read<AppState>().api;
    await api.rejectMemory(id);
    await _refresh();
  }

  Future<void> _makeTemporary(String id, {String? expiresAt}) async {
    final api = context.read<AppState>().api;
    await api.makeMemoryTemporary(id, expiresAt: expiresAt);
    await _refresh();
  }

  Future<void> _makePermanent(String id) async {
    final api = context.read<AppState>().api;
    await api.makeMemoryPermanent(id);
    await _refresh();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFFAF9F5),
      floatingActionButton: FloatingActionButton(
        onPressed: () => _editMemory(),
        backgroundColor: const Color(0xFFFFC815),
        foregroundColor: Colors.white,
        child: const Icon(Icons.add_rounded),
      ),
      body: DefaultTabController(
        length: 2,
        child: SafeArea(
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
                            'Memory Control Center',
                            style: TextStyle(
                              fontFamily: 'Manrope',
                              fontSize: 28,
                              fontWeight: FontWeight.w800,
                              color: Color(0xFF1B1C1A),
                            ),
                          ),
                          SizedBox(height: 2),
                          Text(
                            'View, review, edit, export, and manage remembered context',
                            style: TextStyle(
                              fontSize: 13,
                              color: Color(0xFF575C6B),
                            ),
                          ),
                        ],
                      ),
                    ),
                    TextButton.icon(
                      onPressed: _exportMemories,
                      icon: const Icon(Icons.download_rounded, size: 18),
                      label: const Text('Export'),
                    ),
                    const SizedBox(width: 8),
                    TextButton.icon(
                      onPressed: () {
                        Navigator.of(context).push(
                          MaterialPageRoute(
                            builder: (_) => const MemoryTimelineScreen(),
                          ),
                        );
                      },
                      icon: const Icon(Icons.timeline_rounded, size: 18),
                      label: const Text('Timeline'),
                    ),
                    const SizedBox(width: 8),
                    TextButton(
                      onPressed: _clearHistory,
                      child: const Text('Clear'),
                    ),
                  ],
                ),
              ),
              const Padding(
                padding: EdgeInsets.symmetric(horizontal: 20),
                child: TabBar(
                  labelColor: Color(0xFFFFC815),
                  unselectedLabelColor: Color(0xFF6D6655),
                  indicatorColor: Color(0xFFFFC815),
                  tabs: [
                    Tab(text: 'All memories'),
                    Tab(text: 'Pending review'),
                  ],
                ),
              ),
              Expanded(
                child: RefreshIndicator(
                  onRefresh: _refresh,
                  child: TabBarView(
                    children: [
                      FutureBuilder<List<dynamic>>(
                        future: _memoriesFuture,
                        builder: (context, snapshot) {
                          final memories = snapshot.data ?? const [];
                          if (snapshot.connectionState ==
                              ConnectionState.waiting) {
                            return const Center(
                              child: CircularProgressIndicator(),
                            );
                          }
                          return _MemoryList(
                            memories: memories,
                            emptyState: const _EmptyState(),
                            showPendingActions: false,
                            onEdit: _editMemory,
                            onDelete: _deleteMemory,
                            onPause: _togglePause,
                            onApprove: _approveMemory,
                            onReject: _rejectMemory,
                            onMakeTemporary: _makeTemporary,
                            onMakePermanent: _makePermanent,
                          );
                        },
                      ),
                      FutureBuilder<List<dynamic>>(
                        future: _pendingFuture,
                        builder: (context, snapshot) {
                          final memories = snapshot.data ?? const [];
                          if (snapshot.connectionState ==
                              ConnectionState.waiting) {
                            return const Center(
                              child: CircularProgressIndicator(),
                            );
                          }
                          return _MemoryList(
                            memories: memories,
                            emptyState: const _EmptyState(
                              text: 'No pending memories right now.',
                            ),
                            showPendingActions: true,
                            onEdit: _editMemory,
                            onDelete: _deleteMemory,
                            onPause: _togglePause,
                            onApprove: _approveMemory,
                            onReject: _rejectMemory,
                            onMakeTemporary: _makeTemporary,
                            onMakePermanent: _makePermanent,
                          );
                        },
                      ),
                    ],
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

class _MemoryList extends StatelessWidget {
  const _MemoryList({
    required this.memories,
    required this.emptyState,
    required this.showPendingActions,
    required this.onEdit,
    required this.onDelete,
    required this.onPause,
    required this.onApprove,
    required this.onReject,
    required this.onMakeTemporary,
    required this.onMakePermanent,
  });

  final List<dynamic> memories;
  final Widget emptyState;
  final bool showPendingActions;
  final void Function([Map<String, dynamic>? memory]) onEdit;
  final void Function(String id) onDelete;
  final void Function(Map<String, dynamic> memory) onPause;
  final Future<void> Function(String id) onApprove;
  final Future<void> Function(String id) onReject;
  final Future<void> Function(String id, {String? expiresAt}) onMakeTemporary;
  final Future<void> Function(String id) onMakePermanent;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
      children: [
        _SummaryCard(count: memories.length),
        const SizedBox(height: 16),
        if (memories.isEmpty)
          emptyState
        else
          ...memories.map(
            (memory) => _MemoryCard(
              memory: memory.cast<String, dynamic>(),
              showPendingActions: showPendingActions,
              onEdit: () => onEdit(memory.cast<String, dynamic>()),
              onDelete: () => onDelete(memory['id'].toString()),
              onPause: () => onPause(memory.cast<String, dynamic>()),
              onApprove: () => onApprove(memory['id'].toString()),
              onReject: () => onReject(memory['id'].toString()),
              onMakeTemporary: () => onMakeTemporary(memory['id'].toString()),
              onMakePermanent: () => onMakePermanent(memory['id'].toString()),
            ),
          ),
      ],
    );
  }
}

class _MemoryCard extends StatelessWidget {
  const _MemoryCard({
    required this.memory,
    required this.showPendingActions,
    required this.onEdit,
    required this.onDelete,
    required this.onPause,
    required this.onApprove,
    required this.onReject,
    required this.onMakeTemporary,
    required this.onMakePermanent,
  });

  final Map<String, dynamic> memory;
  final bool showPendingActions;
  final VoidCallback onEdit;
  final VoidCallback onDelete;
  final VoidCallback onPause;
  final Future<void> Function() onApprove;
  final Future<void> Function() onReject;
  final Future<void> Function() onMakeTemporary;
  final Future<void> Function() onMakePermanent;

  @override
  Widget build(BuildContext context) {
    final paused = memory['paused'] as bool? ?? false;
    final sensitive = memory['sensitive'] as bool? ?? false;
    final approved = memory['user_approved'] as bool? ?? true;
    final approvalStatus =
        memory['approval_status']?.toString() ??
        (approved ? 'approved' : 'pending');
    final memoryScope = memory['memory_scope']?.toString() ?? 'permanent';
    final expiresAt = memory['expires_at']?.toString();
    final suggestedReason = memory['suggested_reason']?.toString();
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.7),
        borderRadius: BorderRadius.circular(26),
        border: Border.all(color: Colors.white.withValues(alpha: 0.9)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  memory['title']?.toString() ?? 'Untitled memory',
                  style: const TextStyle(
                    fontFamily: 'Manrope',
                    fontSize: 18,
                    fontWeight: FontWeight.w800,
                    color: Color(0xFF1B1C1A),
                  ),
                ),
              ),
              if (paused)
                const _StatusChip(label: 'Paused', color: Color(0xFF003B2B))
              else
                const _StatusChip(label: 'Active', color: Color(0xFFFFC815)),
              _StatusChip(
                label: approvalStatus,
                color: approvalStatus == 'approved'
                    ? const Color(0xFF003B2B)
                    : approvalStatus == 'pending'
                    ? const Color(0xFF8A5A00)
                    : const Color(0xFFBA1A1A),
              ),
              _StatusChip(label: memoryScope, color: const Color(0xFF5F5B66)),
            ],
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _StatusChip(
                label: memory['type']?.toString() ?? 'fact',
                color: const Color(0xFF1B1C1A),
              ),
              if (memory['life_area'] != null &&
                  memory['life_area'].toString().isNotEmpty)
                _StatusChip(
                  label: memory['life_area'].toString(),
                  color: const Color(0xFF003B2B),
                ),
              if (sensitive)
                const _StatusChip(label: 'Sensitive', color: Color(0xFFBA1A1A)),
              if (!approved)
                const _StatusChip(
                  label: 'Needs approval',
                  color: Color(0xFFBA1A1A),
                ),
            ],
          ),
          const SizedBox(height: 10),
          Text(
            memory['content']?.toString() ?? '',
            style: const TextStyle(
              fontSize: 13.5,
              height: 1.5,
              color: Color(0xFF4B444D),
            ),
          ),
          if (suggestedReason != null && suggestedReason.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(
              suggestedReason,
              style: const TextStyle(
                fontSize: 12.5,
                height: 1.4,
                color: Color(0xFF575C6B),
              ),
            ),
          ],
          if (expiresAt != null && expiresAt.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(
              memoryScope == 'temporary'
                  ? 'Expires: $expiresAt'
                  : 'Expires: $expiresAt',
              style: const TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w700,
                color: Color(0xFF003B2B),
              ),
            ),
          ],
          const SizedBox(height: 14),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              if (showPendingActions)
                FilledButton(
                  onPressed: () => onApprove(),
                  child: const Text('Approve'),
                ),
              if (showPendingActions)
                OutlinedButton(
                  onPressed: () => onReject(),
                  child: const Text('Reject'),
                ),
              OutlinedButton(onPressed: onEdit, child: const Text('Edit')),
              OutlinedButton(
                onPressed: onPause,
                child: Text(paused ? 'Resume' : 'Pause'),
              ),
              if (!showPendingActions)
                FilledButton.tonal(
                  onPressed: onDelete,
                  child: const Text('Delete'),
                ),
              if (!showPendingActions && memoryScope == 'permanent')
                OutlinedButton(
                  onPressed: () => onMakeTemporary(),
                  child: const Text('Make temporary'),
                ),
              if (!showPendingActions && memoryScope == 'temporary')
                OutlinedButton(
                  onPressed: () => onMakePermanent(),
                  child: const Text('Make permanent'),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

class _MemoryEditorSheet extends StatelessWidget {
  const _MemoryEditorSheet({
    required this.titleController,
    required this.contentController,
    required this.typeController,
    required this.lifeAreaController,
    required this.importanceController,
    required this.confidenceController,
    required this.expiresAtController,
    required this.reasonController,
    required this.memoryScope,
    required this.approvalStatus,
    required this.sensitive,
    required this.approved,
    required this.paused,
    required this.onMemoryScopeChanged,
    required this.onApprovalStatusChanged,
    required this.onSensitiveChanged,
    required this.onApprovedChanged,
    required this.onPausedChanged,
  });

  final TextEditingController titleController;
  final TextEditingController contentController;
  final TextEditingController typeController;
  final TextEditingController lifeAreaController;
  final TextEditingController importanceController;
  final TextEditingController confidenceController;
  final TextEditingController expiresAtController;
  final TextEditingController reasonController;
  final String memoryScope;
  final String approvalStatus;
  final bool sensitive;
  final bool approved;
  final bool paused;
  final ValueChanged<String> onMemoryScopeChanged;
  final ValueChanged<String> onApprovalStatusChanged;
  final ValueChanged<bool> onSensitiveChanged;
  final ValueChanged<bool> onApprovedChanged;
  final ValueChanged<bool> onPausedChanged;

  @override
  Widget build(BuildContext context) {
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
          border: Border.all(color: Colors.white.withValues(alpha: 0.9)),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const _SheetHandle(),
            const SizedBox(height: 18),
            _Field(controller: titleController, label: 'Title'),
            const SizedBox(height: 12),
            _Field(
              controller: contentController,
              label: 'Content',
              maxLines: 4,
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: _Field(controller: typeController, label: 'Type'),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: _Field(
                    controller: lifeAreaController,
                    label: 'Life area',
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: _Field(
                    controller: importanceController,
                    label: 'Importance',
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: _Field(
                    controller: confidenceController,
                    label: 'Confidence',
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(
                  child: DropdownButtonFormField<String>(
                    initialValue: memoryScope,
                    decoration: const InputDecoration(
                      labelText: 'Memory scope',
                    ),
                    items: const [
                      DropdownMenuItem(
                        value: 'permanent',
                        child: Text('Permanent'),
                      ),
                      DropdownMenuItem(
                        value: 'temporary',
                        child: Text('Temporary'),
                      ),
                    ],
                    onChanged: (value) {
                      if (value != null) onMemoryScopeChanged(value);
                    },
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: _Field(
                    controller: expiresAtController,
                    label: 'Expires at (ISO)',
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            _Field(
              controller: reasonController,
              label: 'Suggested reason',
              maxLines: 2,
            ),
            const SizedBox(height: 12),
            DropdownButtonFormField<String>(
              initialValue: approvalStatus,
              decoration: const InputDecoration(labelText: 'Approval status'),
              items: const [
                DropdownMenuItem(value: 'approved', child: Text('Approved')),
                DropdownMenuItem(value: 'pending', child: Text('Pending')),
                DropdownMenuItem(value: 'rejected', child: Text('Rejected')),
                DropdownMenuItem(value: 'expired', child: Text('Expired')),
              ],
              onChanged: (value) {
                if (value != null) onApprovalStatusChanged(value);
              },
            ),
            const SizedBox(height: 10),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Sensitive'),
              value: sensitive,
              onChanged: onSensitiveChanged,
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Approved for use'),
              value: approved,
              onChanged: onApprovedChanged,
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Paused'),
              value: paused,
              onChanged: onPausedChanged,
            ),
            const SizedBox(height: 10),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                onPressed: () {
                  Navigator.pop(context, {
                    'title': titleController.text.trim(),
                    'content': contentController.text.trim(),
                    'type': typeController.text.trim(),
                    'life_area': lifeAreaController.text.trim(),
                    'importance':
                        int.tryParse(importanceController.text.trim()) ?? 1,
                    'confidence':
                        double.tryParse(confidenceController.text.trim()) ??
                        0.5,
                    'expires_at': expiresAtController.text.trim(),
                    'suggested_reason': reasonController.text.trim(),
                    'sensitive': sensitive,
                    'user_approved': approved,
                    'paused': paused,
                  });
                },
                child: const Text('Save Memory'),
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

class _SummaryCard extends StatelessWidget {
  const _SummaryCard({required this.count});

  final int count;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFFF4F1EB),
        borderRadius: BorderRadius.circular(22),
      ),
      child: Text(
        '$count saved memory${count == 1 ? '' : 's'}',
        style: const TextStyle(
          fontWeight: FontWeight.w700,
          color: Color(0xFF1B1C1A),
        ),
      ),
    );
  }
}

class _StatusChip extends StatelessWidget {
  const _StatusChip({required this.label, required this.color});

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w800,
          color: color,
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
  const _EmptyState({
    this.text =
        'No memories saved yet. AiPal will start collecting useful context as you talk.',
  });

  final String text;
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.6),
        borderRadius: BorderRadius.circular(24),
      ),
      child: Text(
        text,
        style: const TextStyle(
          fontSize: 14,
          height: 1.5,
          color: Color(0xFF4B444D),
        ),
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
