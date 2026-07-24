import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config.dart';

class ApiClient {
  ApiClient(this.token);

  static const _timeout = Duration(seconds: 12);
  static const _textTurnTimeout = Duration(seconds: 90);
  static const _audioTurnTimeout = Duration(seconds: 60);

  final String? token;

  Map<String, String> get _headers => {
    'Content-Type': 'application/json',
    if (token != null) 'Authorization': 'Bearer $token',
  };

  Future<http.Response> _get(Uri uri) =>
      http.get(uri, headers: _headers).timeout(_timeout);

  Future<http.Response> _post(Uri uri, {Object? body}) =>
      http.post(uri, headers: _headers, body: body).timeout(_timeout);

  Future<http.Response> _postTextTurn(Uri uri, {Object? body}) =>
      http.post(uri, headers: _headers, body: body).timeout(_textTurnTimeout);

  Future<http.Response> _put(Uri uri, {Object? body}) =>
      http.put(uri, headers: _headers, body: body).timeout(_timeout);

  Future<http.Response> _patch(Uri uri, {Object? body}) =>
      http.patch(uri, headers: _headers, body: body).timeout(_timeout);

  Future<Map<String, dynamic>> register(String email) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/auth/register'),
      body: jsonEncode({'email': email}),
    );
    _throwIfFailed(r, 'Registration failed');
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> verify(String magicToken) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/auth/verify'),
      body: jsonEncode({'token': magicToken}),
    );
    _throwIfFailed(r, 'Verification failed');
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  void _throwIfFailed(http.Response response, String fallback) {
    if (response.statusCode >= 200 && response.statusCode < 300) return;
    var message = fallback;
    try {
      final decoded = jsonDecode(response.body);
      if (decoded is Map<String, dynamic>) {
        message =
            decoded['detail']?.toString() ??
            decoded['message']?.toString() ??
            fallback;
      }
    } catch (_) {
      if (response.body.trim().isNotEmpty) {
        message = response.body.trim();
      }
    }
    throw Exception('$message (${response.statusCode})');
  }

  Future<Map<String, dynamic>> getProfile() async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/profile'));
    _throwIfFailed(r, 'Profile load failed');
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> updateProfile(Map<String, dynamic> body) async {
    final r = await _put(
      Uri.parse('${AppConfig.apiBase}/profile'),
      body: jsonEncode(body),
    );
    _throwIfFailed(r, 'Profile update failed');
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<List<dynamic>> listTasks({String? goalId}) async {
    final uri = Uri.parse(
      '${AppConfig.apiBase}/tasks',
    ).replace(queryParameters: goalId == null ? null : {'goal_id': goalId});
    final r = await _get(uri);
    return jsonDecode(r.body) as List<dynamic>;
  }

  Future<Map<String, dynamic>> createTask(
    String title, {
    String? notes,
    String? goalId,
  }) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/tasks'),
      body: jsonEncode({
        'title': title,
        if (notes != null && notes.trim().isNotEmpty) 'notes': notes.trim(),
        if (goalId != null) 'goal_id': goalId,
        'source': 'text',
      }),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> patchTask(
    int id, {
    String? status,
    Map<String, dynamic>? extra,
  }) async {
    final body = <String, dynamic>{...?extra};
    if (status != null) {
      body['status'] = status;
    }
    final r = await _patch(
      Uri.parse('${AppConfig.apiBase}/tasks/$id'),
      body: jsonEncode(body),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<void> deleteTask(int id) async {
    await http
        .delete(Uri.parse('${AppConfig.apiBase}/tasks/$id'), headers: _headers)
        .timeout(_timeout);
  }

  Future<Map<String, dynamic>> fetchTaskTodayView() async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/tasks/today-view'));
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> fetchTodayView() => getTodayAgenda();

  Future<Map<String, dynamic>> getTodaySummary() async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/today/summary'));
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getTodayAgenda({String? day}) async {
    final uri = Uri.parse(
      '${AppConfig.apiBase}/today/agenda',
    ).replace(queryParameters: day == null ? null : {'day': day});
    final r = await _get(uri);
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<List<dynamic>> getTodayItemRange({
    required String startDate,
    required String endDate,
  }) async {
    final uri = Uri.parse(
      '${AppConfig.apiBase}/today-items/range',
    ).replace(queryParameters: {'start_date': startDate, 'end_date': endDate});
    final r = await _get(uri);
    return jsonDecode(r.body) as List<dynamic>;
  }

  Future<Map<String, dynamic>> sendTodaySummary() async {
    final r = await _post(Uri.parse('${AppConfig.apiBase}/today/summary/send'));
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getNextTodayItem() async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/today/next'));
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> notifyNextTodayItem() async {
    final r = await _post(Uri.parse('${AppConfig.apiBase}/today/next/notify'));
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> generatePlannerDraft(String kind) async {
    final endpoint = switch (kind) {
      'daily' => 'daily',
      'weekly' => 'weekly',
      'monthly' => 'monthly',
      'quarterly' => 'quarterly',
      '90-day' => '90-day',
      'life-roadmap' => 'life-roadmap',
      _ => 'daily',
    };
    final r = await _post(Uri.parse('${AppConfig.apiBase}/planner/$endpoint'));
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> confirmPlannerDraft({
    String draftId = 'current',
  }) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/planner/$draftId/confirm'),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<List<dynamic>> getMeetings({bool upcoming = false}) async {
    final r = await _get(
      Uri.parse('${AppConfig.apiBase}/meetings${upcoming ? '/upcoming' : ''}'),
    );
    return jsonDecode(r.body) as List<dynamic>;
  }

  Future<Map<String, dynamic>> createMeeting(Map<String, dynamic> body) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/meetings'),
      body: jsonEncode(body),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getMeetingBrief(String id) async {
    final r = await _post(Uri.parse('${AppConfig.apiBase}/meetings/$id/brief'));
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> addMeetingNotes(
    String id,
    String content,
  ) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/meetings/$id/notes'),
      body: jsonEncode({'content': content}),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> summarizeMeeting(String id) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/meetings/$id/summarize'),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getMeetingFollowups(String id) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/meetings/$id/followups'),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<List<dynamic>> getTodayItems({String? day}) async {
    final uri = Uri.parse(
      '${AppConfig.apiBase}/today-items',
    ).replace(queryParameters: day == null ? null : {'day': day});
    final r = await _get(uri);
    return jsonDecode(r.body) as List<dynamic>;
  }

  Future<Map<String, dynamic>> createTodayItem(
    Map<String, dynamic> body,
  ) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/today-items'),
      body: jsonEncode(body),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> updateTodayItem(
    String id,
    Map<String, dynamic> body,
  ) async {
    final r = await _patch(
      Uri.parse('${AppConfig.apiBase}/today-items/$id'),
      body: jsonEncode(body),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> completeTodayItem(String id) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/today-items/$id/complete'),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> cancelTodayItem(String id) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/today-items/$id/cancel'),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> snoozeTodayItem(
    String id, {
    int minutes = 30,
  }) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/today-items/$id/snooze'),
      body: jsonEncode({'minutes': minutes}),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> rescheduleTodayItem(
    String id,
    DateTime newTime,
  ) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/today-items/$id/reschedule'),
      body: jsonEncode({'new_time': newTime.toIso8601String()}),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> startFocusTodayItem(String id) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/today-items/$id/start-focus'),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> startFocusSession(String todayItemId) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/focus/today-items/$todayItemId/start'),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> pauseFocusSession(String sessionId) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/focus/sessions/$sessionId/pause'),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> resumeFocusSession(String sessionId) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/focus/sessions/$sessionId/resume'),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> endFocusSession(
    String sessionId, {
    String? notes,
  }) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/focus/sessions/$sessionId/end'),
      body: jsonEncode({if (notes != null) 'notes': notes}),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<List<dynamic>> getNotifications() async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/notifications'));
    return jsonDecode(r.body) as List<dynamic>;
  }

  Future<Map<String, dynamic>> markNotificationRead(String id) async {
    final r = await _patch(
      Uri.parse('${AppConfig.apiBase}/notifications/$id/read'),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> dismissNotification(String id) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/notifications/$id/dismiss'),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getNotificationPreferences() async {
    final r = await _get(
      Uri.parse('${AppConfig.apiBase}/notification-preferences'),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> updateNotificationPreferences(
    Map<String, dynamic> body,
  ) async {
    final r = await _patch(
      Uri.parse('${AppConfig.apiBase}/notification-preferences'),
      body: jsonEncode(body),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getTaskDetail(String id) async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/tasks/$id/detail'));
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<void> reorderTasks(List<int> orderedIds) async {
    await _post(
      Uri.parse('${AppConfig.apiBase}/tasks/reorder'),
      body: jsonEncode({'ordered_ids': orderedIds}),
    );
  }

  Future<List<dynamic>> breakdownTask(int id) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/tasks/$id/breakdown'),
    );
    return jsonDecode(r.body) as List<dynamic>;
  }

  Future<int> deferOpenTasks() async {
    final r = await _post(Uri.parse('${AppConfig.apiBase}/tasks/defer-open'));
    return (jsonDecode(r.body) as Map<String, dynamic>)['deferred'] as int? ??
        0;
  }

  Future<Map<String, dynamic>> taskSummary() async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/tasks/summary'));
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> morningPayload() async {
    final r = await _get(
      Uri.parse('${AppConfig.apiBase}/daily/morning-payload'),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> eveningPayload() async {
    final r = await _get(
      Uri.parse('${AppConfig.apiBase}/daily/evening-payload'),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> textTurn(
    String text, {
    String? sessionId,
  }) async {
    final r = await _postTextTurn(
      Uri.parse('${AppConfig.apiBase}/turn/text'),
      body: jsonEncode({
        'text': text,
        if (sessionId != null) 'session_id': sessionId,
      }),
    );
    _throwIfFailed(r, 'Text turn failed');
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> companionTurn(
    String message, {
    String? conversationId,
    String source = 'text',
    Map<String, dynamic>? sourceContext,
  }) async {
    final r = await _postTextTurn(
      Uri.parse('${AppConfig.apiBase}/companion/turn'),
      body: jsonEncode({
        'message': message,
        if (conversationId != null) 'conversation_id': conversationId,
        'source': source,
        if (sourceContext != null) 'source_context': sourceContext,
      }),
    );
    _throwIfFailed(r, 'Companion reply failed');
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getCompanionHome() async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/companion/home'));
    _throwIfFailed(r, 'Companion home failed');
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getLifeMap() async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/life-map'));
    _throwIfFailed(r, 'Life map failed');
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getLifeMapBriefing() async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/life-map/briefing'));
    _throwIfFailed(r, 'Life map briefing failed');
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getLifeAreaDetail(String lifeArea) async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/life-map/$lifeArea'));
    _throwIfFailed(r, 'Life area failed');
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getLifeAreaBriefing(String lifeArea) async {
    final r = await _get(
      Uri.parse('${AppConfig.apiBase}/life-map/$lifeArea/briefing'),
    );
    _throwIfFailed(r, 'Life area briefing failed');
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<List<dynamic>> listConversationSessions() async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/turn/sessions'));
    return jsonDecode(r.body) as List<dynamic>;
  }

  Future<List<dynamic>> getConversationTurns(String sessionId) async {
    final r = await _get(
      Uri.parse('${AppConfig.apiBase}/turn/sessions/$sessionId'),
    );
    return jsonDecode(r.body) as List<dynamic>;
  }

  Future<void> deleteConversationSession(String sessionId) async {
    await http
        .delete(
          Uri.parse('${AppConfig.apiBase}/turn/sessions/$sessionId'),
          headers: _headers,
        )
        .timeout(_timeout);
  }

  Future<List<dynamic>> listConversations() async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/conversations'));
    return jsonDecode(r.body) as List<dynamic>;
  }

  Future<void> deleteConversation(String id) async {
    await http
        .delete(
          Uri.parse('${AppConfig.apiBase}/conversations/$id'),
          headers: _headers,
        )
        .timeout(_timeout);
  }

  Future<Map<String, dynamic>> clearConversationHistory() async {
    final r = await http
        .delete(
          Uri.parse('${AppConfig.apiBase}/conversation-history'),
          headers: _headers,
        )
        .timeout(_timeout);
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<List<dynamic>> listMemories() async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/memory'));
    return jsonDecode(r.body) as List<dynamic>;
  }

  Future<List<dynamic>> listPendingMemories() async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/memory/pending'));
    return jsonDecode(r.body) as List<dynamic>;
  }

  Future<Map<String, dynamic>> createMemory(Map<String, dynamic> body) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/memory'),
      body: jsonEncode(body),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<void> updateMemory(String id, Map<String, dynamic> body) async {
    await _patch(
      Uri.parse('${AppConfig.apiBase}/memory/$id'),
      body: jsonEncode(body),
    );
  }

  Future<void> editMemory(String id, Map<String, dynamic> body) async {
    await _patch(
      Uri.parse('${AppConfig.apiBase}/memory/$id/edit'),
      body: jsonEncode(body),
    );
  }

  Future<Map<String, dynamic>> approveMemory(String id) async {
    final r = await _post(Uri.parse('${AppConfig.apiBase}/memory/$id/approve'));
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> rejectMemory(String id) async {
    final r = await _post(Uri.parse('${AppConfig.apiBase}/memory/$id/reject'));
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> makeMemoryTemporary(
    String id, {
    String? expiresAt,
  }) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/memory/$id/make-temporary'),
      body: jsonEncode({if (expiresAt != null) 'expires_at': expiresAt}),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> makeMemoryPermanent(String id) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/memory/$id/make-permanent'),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<void> deleteMemory(String id) async {
    await http
        .delete(Uri.parse('${AppConfig.apiBase}/memory/$id'), headers: _headers)
        .timeout(_timeout);
  }

  Future<void> pauseMemory(String id, {bool paused = true}) async {
    await _post(
      Uri.parse(
        '${AppConfig.apiBase}/memory/$id/${paused ? 'pause' : 'resume'}',
      ),
    );
  }

  Future<List<dynamic>> searchMemory(String query, {int limit = 8}) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/memory/search'),
      body: jsonEncode({'query': query, 'limit': limit}),
    );
    return jsonDecode(r.body) as List<dynamic>;
  }

  Future<List<dynamic>> exportMemories() async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/memory/export'));
    return jsonDecode(r.body) as List<dynamic>;
  }

  Future<List<dynamic>> getMemoryTimeline({
    String? lifeArea,
    String? type,
    String? startDate,
    String? endDate,
    int limit = 100,
  }) async {
    final params = <String, String>{
      'limit': '$limit',
      if (lifeArea != null && lifeArea.isNotEmpty) 'life_area': lifeArea,
      if (type != null && type.isNotEmpty) 'type': type,
      if (startDate != null && startDate.isNotEmpty) 'start_date': startDate,
      if (endDate != null && endDate.isNotEmpty) 'end_date': endDate,
    };
    final r = await _get(
      Uri.parse(
        '${AppConfig.apiBase}/memory/timeline',
      ).replace(queryParameters: params),
    );
    return (jsonDecode(r.body) as Map<String, dynamic>)['items']
        as List<dynamic>;
  }

  Future<Map<String, dynamic>> getMemoryAutobiography({int limit = 300}) async {
    final r = await _get(
      Uri.parse(
        '${AppConfig.apiBase}/memory/autobiography',
      ).replace(queryParameters: {'limit': '$limit'}),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<List<dynamic>> listKnowledgeEntities({String? entityType}) async {
    final uri = Uri.parse('${AppConfig.apiBase}/knowledge/entities').replace(
      queryParameters: entityType == null || entityType.isEmpty
          ? null
          : {'entity_type': entityType},
    );
    final r = await _get(uri);
    return jsonDecode(r.body) as List<dynamic>;
  }

  Future<Map<String, dynamic>> getKnowledgeEntity(String id) async {
    final r = await _get(
      Uri.parse('${AppConfig.apiBase}/knowledge/entities/$id'),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getKnowledgeGraph(String id) async {
    final r = await _get(
      Uri.parse('${AppConfig.apiBase}/knowledge/entities/$id/graph'),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<List<dynamic>> searchKnowledge(
    String query, {
    String? entityType,
  }) async {
    final uri = Uri.parse('${AppConfig.apiBase}/knowledge/search').replace(
      queryParameters: {
        'query': query,
        if (entityType != null && entityType.isNotEmpty)
          'entity_type': entityType,
      },
    );
    final r = await _get(uri);
    return jsonDecode(r.body) as List<dynamic>;
  }

  Future<Map<String, dynamic>> getKnowledgeSummary() async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/knowledge/summary'));
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> rebuildKnowledgeGraph() async {
    final r = await _post(Uri.parse('${AppConfig.apiBase}/knowledge/rebuild'));
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<List<dynamic>> getDueFollowups() async {
    final r = await _get(
      Uri.parse('${AppConfig.apiBase}/relationship/followups/due'),
    );
    return jsonDecode(r.body) as List<dynamic>;
  }

  Future<List<dynamic>> getCommitments() async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/commitments'));
    return jsonDecode(r.body) as List<dynamic>;
  }

  Future<List<dynamic>> getDueCommitments() async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/commitments/due'));
    return jsonDecode(r.body) as List<dynamic>;
  }

  Future<Map<String, dynamic>> createCommitment(
    Map<String, dynamic> body,
  ) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/commitments'),
      body: jsonEncode(body),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> updateCommitment(
    String id,
    Map<String, dynamic> body,
  ) async {
    final r = await _patch(
      Uri.parse('${AppConfig.apiBase}/commitments/$id'),
      body: jsonEncode(body),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> completeCommitment(String id) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/commitments/$id/complete'),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> dismissCommitment(String id) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/commitments/$id/dismiss'),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> completeFollowup(String memoryId) async {
    final r = await _post(
      Uri.parse(
        '${AppConfig.apiBase}/relationship/followups/$memoryId/complete',
      ),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> dismissFollowup(String memoryId) async {
    final r = await _post(
      Uri.parse(
        '${AppConfig.apiBase}/relationship/followups/$memoryId/dismiss',
      ),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getLifeAreaInsights() async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/insights/life-areas'));
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getCompanionScore() async {
    final r = await _get(
      Uri.parse('${AppConfig.apiBase}/insights/companion-score'),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getWeeklyInsights() async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/insights/weekly'));
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getMonthlyInsights() async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/insights/monthly'));
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getDeepLifeAreaInsights() async {
    final r = await _get(
      Uri.parse('${AppConfig.apiBase}/insights/life-areas/deep'),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> coachDecision(
    String question, {
    List<String>? options,
  }) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/coaching/decision'),
      body: jsonEncode({
        'question': question,
        if (options != null) 'options': options,
      }),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<List<dynamic>> listCoachingDecisions() async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/coaching/decisions'));
    return jsonDecode(r.body) as List<dynamic>;
  }

  Future<Map<String, dynamic>> getCoachingDecision(String id) async {
    final r = await _get(
      Uri.parse('${AppConfig.apiBase}/coaching/decisions/$id'),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> applyFramework(
    String framework,
    String prompt,
  ) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/coaching/framework'),
      body: jsonEncode({'framework': framework, 'prompt': prompt}),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<List<dynamic>> listFrameworks() async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/coaching/frameworks'));
    return (jsonDecode(r.body) as Map<String, dynamic>)['frameworks']
        as List<dynamic>;
  }

  Future<Map<String, dynamic>> createGrowthPlan({
    String? goalId,
    String horizon = '30_day',
    String? title,
  }) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/growth-plans'),
      body: jsonEncode({
        if (goalId != null) 'goal_id': goalId,
        'horizon': horizon,
        if (title != null) 'title': title,
      }),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<List<dynamic>> listGrowthPlans() async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/growth-plans'));
    return jsonDecode(r.body) as List<dynamic>;
  }

  Future<Map<String, dynamic>> getGrowthPlan(String id) async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/growth-plans/$id'));
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> updateGrowthPlan(
    String id,
    Map<String, dynamic> body,
  ) async {
    final r = await _patch(
      Uri.parse('${AppConfig.apiBase}/growth-plans/$id'),
      body: jsonEncode(body),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> createAccountabilitySnapshot({
    required String periodStart,
    required String periodEnd,
  }) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/accountability/snapshot'),
      body: jsonEncode({'period_start': periodStart, 'period_end': periodEnd}),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getLatestAccountabilitySnapshot() async {
    final r = await _get(
      Uri.parse('${AppConfig.apiBase}/accountability/latest'),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> compareAccountability(
    Map<String, dynamic> body,
  ) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/accountability/compare'),
      body: jsonEncode(body),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> createHabit(Map<String, dynamic> body) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/habits'),
      body: jsonEncode(body),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<List<dynamic>> listHabits() async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/habits'));
    return jsonDecode(r.body) as List<dynamic>;
  }

  Future<Map<String, dynamic>> logHabit(
    String habitId,
    Map<String, dynamic> body,
  ) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/habits/$habitId/log'),
      body: jsonEncode(body),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getHabitSummary() async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/habits/summary'));
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>?> getLatestWeeklyReview() async {
    final r = await _get(
      Uri.parse('${AppConfig.apiBase}/reflections/weekly/latest'),
    );
    if (r.statusCode == 200 &&
        r.body.trim().isNotEmpty &&
        r.body.trim() != 'null') {
      return jsonDecode(r.body) as Map<String, dynamic>;
    }
    return null;
  }

  Future<Map<String, dynamic>> generateWeeklyReview() async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/reflections/weekly/generate'),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<List<dynamic>> listGoals() async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/goals'));
    return jsonDecode(r.body) as List<dynamic>;
  }

  Future<Map<String, dynamic>> createGoal(Map<String, dynamic> body) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/goals'),
      body: jsonEncode(body),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getGoal(String id) async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/goals/$id'));
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<void> updateGoal(String id, Map<String, dynamic> body) async {
    await _patch(
      Uri.parse('${AppConfig.apiBase}/goals/$id'),
      body: jsonEncode(body),
    );
  }

  Future<void> deleteGoal(String id) async {
    await http
        .delete(Uri.parse('${AppConfig.apiBase}/goals/$id'), headers: _headers)
        .timeout(_timeout);
  }

  Future<List<dynamic>> listReflections({String? goalId}) async {
    final uri = Uri.parse(
      '${AppConfig.apiBase}/reflections',
    ).replace(queryParameters: goalId == null ? null : {'goal_id': goalId});
    final r = await _get(uri);
    return jsonDecode(r.body) as List<dynamic>;
  }

  Future<Map<String, dynamic>> createReflection(
    Map<String, dynamic> body,
  ) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/reflections'),
      body: jsonEncode(body),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<void> updateReflection(String id, Map<String, dynamic> body) async {
    await _patch(
      Uri.parse('${AppConfig.apiBase}/reflections/$id'),
      body: jsonEncode(body),
    );
  }

  Future<void> deleteReflection(String id) async {
    await http
        .delete(
          Uri.parse('${AppConfig.apiBase}/reflections/$id'),
          headers: _headers,
        )
        .timeout(_timeout);
  }

  Future<Map<String, dynamic>> getGoalDetail(String id) async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/goals/$id/detail'));
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getReflectionDetail(String id) async {
    final r = await _get(
      Uri.parse('${AppConfig.apiBase}/reflections/$id/detail'),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>?> suggestDay({String? template}) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/tasks/suggest-day'),
      body: jsonEncode({if (template != null) 'template': template}),
    );
    if (r.statusCode >= 400) {
      throw Exception('Suggest day failed (${r.statusCode}): ${r.body}');
    }
    final body = jsonDecode(r.body) as Map<String, dynamic>;
    return body['plan_draft'] as Map<String, dynamic>?;
  }

  Future<Map<String, dynamic>?> fetchPlanDraft() async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/tasks/plan-draft'));
    if (r.statusCode == 200 &&
        r.body.trim().isNotEmpty &&
        r.body.trim() != 'null') {
      return jsonDecode(r.body) as Map<String, dynamic>;
    }
    return null;
  }

  Future<List<dynamic>> confirmPlanDraft() async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/tasks/plan-draft/confirm'),
    );
    final body = jsonDecode(r.body) as Map<String, dynamic>;
    return (body['created'] as List?) ?? [];
  }

  Future<void> discardPlanDraft() async {
    await _post(Uri.parse('${AppConfig.apiBase}/tasks/plan-draft/discard'));
  }

  Future<Map<String, dynamic>> liveGreeting({
    bool inLive = false,
    bool wakeEnabled = false,
    bool showWakeIntro = false,
  }) async {
    final params = <String, String>{};
    if (inLive) params['in_live'] = 'true';
    if (wakeEnabled) params['wake_enabled'] = 'true';
    if (showWakeIntro) params['show_wake_intro'] = 'true';
    final uri = Uri.parse(
      '${AppConfig.apiBase}/daily/live-greeting',
    ).replace(queryParameters: params.isEmpty ? null : params);
    final r = await _get(uri);
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> checkinPayload() async {
    final r = await _get(
      Uri.parse('${AppConfig.apiBase}/daily/checkin-payload'),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> taskNudge({
    required int taskId,
    int minutes = 12,
  }) async {
    final uri = Uri.parse(
      '${AppConfig.apiBase}/daily/task-nudge',
    ).replace(queryParameters: {'task_id': '$taskId', 'minutes': '$minutes'});
    final r = await _get(uri);
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> tts(String text, {String? voice}) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/turn/tts'),
      body: jsonEncode({'text': text, if (voice != null) 'voice': voice}),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<List<Map<String, dynamic>>> getTtsVoices() async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/voice/profiles'));
    final decoded = jsonDecode(r.body);
    final list = decoded is Map<String, dynamic>
        ? decoded['profiles'] as List
        : decoded as List;
    return list
        .whereType<Map>()
        .map((item) => item.cast<String, dynamic>())
        .toList();
  }

  Future<Map<String, dynamic>> getVoiceCapabilities() async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/voice/capabilities'));
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> audioTurn(
    List<int> bytes, {
    String filename = 'turn.m4a',
    String? sessionId,
  }) async {
    final req = http.MultipartRequest(
      'POST',
      Uri.parse('${AppConfig.apiBase}/turn/audio'),
    );
    if (token != null) req.headers['Authorization'] = 'Bearer $token';
    if (sessionId != null && sessionId.isNotEmpty) {
      req.fields['session_id'] = sessionId;
    }
    req.files.add(
      http.MultipartFile.fromBytes('file', bytes, filename: filename),
    );
    final streamed = await req.send().timeout(_audioTurnTimeout);
    final body = await streamed.stream.bytesToString();
    if (streamed.statusCode >= 400) {
      throw Exception('Audio turn failed (${streamed.statusCode}): $body');
    }
    return jsonDecode(body) as Map<String, dynamic>;
  }

  Future<int> importCalendar(List<Map<String, dynamic>> events) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/calendar/import'),
      body: jsonEncode({'events': events}),
    );
    return (jsonDecode(r.body) as Map<String, dynamic>)['imported'] as int;
  }

  Future<Map<String, dynamic>> getCompanionPreferences() async {
    final r = await _get(
      Uri.parse('${AppConfig.apiBase}/proactive/companion/preferences'),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> updateCompanionPreferences(
    Map<String, dynamic> body,
  ) async {
    final r = await _patch(
      Uri.parse('${AppConfig.apiBase}/proactive/companion/preferences'),
      body: jsonEncode(body),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<List<dynamic>> listProactivePrompts() async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/proactive/prompts'));
    return jsonDecode(r.body) as List<dynamic>;
  }

  Future<Map<String, dynamic>> generateProactivePrompt({
    bool force = false,
  }) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/proactive/prompts/generate'),
      body: jsonEncode({'force': force}),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> markProactiveDelivered(String id) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/proactive/prompts/$id/delivered'),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> dismissProactivePrompt(String id) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/proactive/prompts/$id/dismiss'),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getEmotionalContinuity() async {
    final r = await _get(
      Uri.parse('${AppConfig.apiBase}/insights/emotional-continuity'),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getUnderstandingProfile() async {
    final r = await _get(
      Uri.parse('${AppConfig.apiBase}/understanding/profile'),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getLifeStory({String period = 'year'}) async {
    final r = await _get(
      Uri.parse(
        '${AppConfig.apiBase}/life-story/accomplishments',
      ).replace(queryParameters: {'period': period}),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getLifeDashboard() async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/life-dashboard'));
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getLivingDashboard() async {
    final r = await _get(
      Uri.parse('${AppConfig.apiBase}/life-dashboard/living'),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<List<dynamic>> listConnectedAccounts() async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/connectors/accounts'));
    return jsonDecode(r.body) as List<dynamic>;
  }

  Future<Map<String, dynamic>> createConnectedAccount(
    Map<String, dynamic> body,
  ) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/connectors/accounts'),
      body: jsonEncode(body),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<void> deleteConnectedAccount(String id) async {
    await http
        .delete(
          Uri.parse('${AppConfig.apiBase}/connectors/accounts/$id'),
          headers: _headers,
        )
        .timeout(_timeout);
  }

  Future<List<dynamic>> listConnectedItems({String? provider}) async {
    final uri = Uri.parse('${AppConfig.apiBase}/connectors/items').replace(
      queryParameters: provider == null ? null : {'provider': provider},
    );
    final r = await _get(uri);
    return jsonDecode(r.body) as List<dynamic>;
  }

  Future<Map<String, dynamic>> importConnectedItem(
    Map<String, dynamic> body,
  ) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/connectors/items/import'),
      body: jsonEncode(body),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> syncEmail(Map<String, dynamic> body) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/connectors/email/sync'),
      body: jsonEncode(body),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<List<dynamic>> listEmailItems() async {
    final r = await _get(
      Uri.parse('${AppConfig.apiBase}/connectors/email/items'),
    );
    return jsonDecode(r.body) as List<dynamic>;
  }

  Future<Map<String, dynamic>> syncCalendar(Map<String, dynamic> body) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/connectors/calendar/sync'),
      body: jsonEncode(body),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<List<dynamic>> listCalendarCommitments() async {
    final r = await _get(
      Uri.parse('${AppConfig.apiBase}/connectors/calendar/commitments'),
    );
    return jsonDecode(r.body) as List<dynamic>;
  }

  Future<Map<String, dynamic>> importDocument(Map<String, dynamic> body) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/connectors/documents/import'),
      body: jsonEncode(body),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<List<dynamic>> listDocumentItems() async {
    final r = await _get(
      Uri.parse('${AppConfig.apiBase}/connectors/documents/items'),
    );
    return jsonDecode(r.body) as List<dynamic>;
  }

  Future<Map<String, dynamic>> summarizeDocument(String id) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/connectors/documents/$id/summarize'),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> importWhatsapp(Map<String, dynamic> body) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/connectors/whatsapp/import-export'),
      body: jsonEncode(body),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<List<dynamic>> listWhatsappItems() async {
    final r = await _get(
      Uri.parse('${AppConfig.apiBase}/connectors/whatsapp/items'),
    );
    return jsonDecode(r.body) as List<dynamic>;
  }

  Future<Map<String, dynamic>> deleteConnectedData({String? provider}) async {
    final uri = Uri.parse('${AppConfig.apiBase}/connectors/data').replace(
      queryParameters: provider == null ? null : {'provider': provider},
    );
    final r = await http.delete(uri, headers: _headers).timeout(_timeout);
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<List<dynamic>> listBusinessProjects() async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/business/projects'));
    return jsonDecode(r.body) as List<dynamic>;
  }

  Future<List<dynamic>> listProjectRooms() async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/project-rooms'));
    return jsonDecode(r.body) as List<dynamic>;
  }

  Future<Map<String, dynamic>> createProjectRoom(
    Map<String, dynamic> body,
  ) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/project-rooms'),
      body: jsonEncode(body),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getProjectRoomSummary(String id) async {
    final r = await _get(
      Uri.parse('${AppConfig.apiBase}/project-rooms/$id/summary'),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> createBusinessProject(
    Map<String, dynamic> body,
  ) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/business/projects'),
      body: jsonEncode(body),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getBusinessProject(String id) async {
    final r = await _get(
      Uri.parse('${AppConfig.apiBase}/business/projects/$id'),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> updateBusinessProject(
    String id,
    Map<String, dynamic> body,
  ) async {
    final r = await _patch(
      Uri.parse('${AppConfig.apiBase}/business/projects/$id'),
      body: jsonEncode(body),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<List<dynamic>> getBusinessProjectEvents(String id) async {
    final r = await _get(
      Uri.parse('${AppConfig.apiBase}/business/projects/$id/events'),
    );
    return jsonDecode(r.body) as List<dynamic>;
  }
}
