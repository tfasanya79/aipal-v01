from datetime import date, datetime, time
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr


class RegisterResponse(BaseModel):
    ok: bool = True
    message: str = "Magic link sent"
    dev_token: str | None = None


class VerifyRequest(BaseModel):
    token: str


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    user_id: UUID


class RefreshRequest(BaseModel):
    refresh_token: str


class ProfileResponse(BaseModel):
    user_id: UUID
    email: str
    display_name: str | None = None
    wake_name: str | None = None
    timezone: str = "UTC"
    about_me: str | None = None
    morning_brief_at: str | None = None
    evening_recap_at: str | None = None
    checkin_enabled: bool = True


class ProfileUpdate(BaseModel):
    display_name: str | None = None
    wake_name: str | None = None
    timezone: str | None = None
    about_me: str | None = None
    morning_brief_at: str | None = None
    evening_recap_at: str | None = None
    checkin_enabled: bool | None = None


class TaskCreate(BaseModel):
    title: str
    notes: str | None = None
    due_at: datetime | None = None
    priority: int = Field(default=1, ge=0, le=3)
    source: str = "text"
    goal_id: UUID | None = None
    parent_task_id: int | None = None
    estimated_minutes: int | None = None
    sort_order: int = 0
    category: str | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    status: str | None = None
    due_at: datetime | None = None
    notes: str | None = None
    estimated_minutes: int | None = None
    sort_order: int | None = None
    category: str | None = None
    goal_id: UUID | None = None


class TaskResponse(BaseModel):
    id: int
    title: str
    notes: str | None
    due_at: datetime | None
    priority: int
    status: str
    source: str
    goal_id: UUID | None = None
    parent_task_id: int | None = None
    estimated_minutes: int | None = None
    sort_order: int = 0
    category: str | None = None
    created_at: datetime
    completed_at: datetime | None
    subtasks: list["TaskResponse"] = Field(default_factory=list)


class TaskReorderRequest(BaseModel):
    ordered_ids: list[int]


class TaskDeleteResponse(BaseModel):
    ok: bool = True


class ConversationSessionSummary(BaseModel):
    session_id: str
    preview: str
    last_role: str
    last_activity_at: datetime
    turn_count: int


class ConversationTurnResponse(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime


class TaskSummary(BaseModel):
    date: str
    total: int
    done: int
    open: int
    deferred: int
    streak_days: int = 0


class TodaySections(BaseModel):
    now: list[TaskResponse] = Field(default_factory=list)
    upcoming: list[TaskResponse] = Field(default_factory=list)
    completed: list[TaskResponse] = Field(default_factory=list)


class TodayItemCreate(BaseModel):
    type: str = "task"
    title: str
    description: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    due_at: datetime | None = None
    status: str = "open"
    priority: str | None = None
    source: str | None = "manual"
    goal_id: UUID | None = None
    task_id: int | None = None
    calendar_event_id: UUID | None = None
    reminder_id: UUID | None = None
    habit_id: UUID | None = None
    reflection_id: UUID | None = None
    commitment_id: UUID | None = None
    metadata: dict | list | None = None
    created_by: str = "user"


class TodayItemUpdate(BaseModel):
    type: str | None = None
    title: str | None = None
    description: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    due_at: datetime | None = None
    status: str | None = None
    priority: str | None = None
    metadata: dict | list | None = None


class TodayItemResponse(BaseModel):
    id: UUID
    user_id: UUID
    type: str
    title: str
    description: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    due_at: datetime | None = None
    status: str = "open"
    priority: str | None = None
    source: str | None = None
    goal_id: UUID | None = None
    task_id: int | None = None
    calendar_event_id: UUID | None = None
    reminder_id: UUID | None = None
    habit_id: UUID | None = None
    reflection_id: UUID | None = None
    commitment_id: UUID | None = None
    metadata: dict | list | None = None
    created_by: str = "aipal"
    created_at: datetime | None = None
    updated_at: datetime | None = None


class TodayViewResponse(BaseModel):
    summary: TaskSummary
    up_next: TaskResponse | None = None
    sections: TodaySections
    today_items: list[TodayItemResponse] = Field(default_factory=list)


class TaskBulkCreate(BaseModel):
    tasks: list[TaskCreate]


class DailyPayload(BaseModel):
    greeting: str
    prompt: str
    summary: TaskSummary | None = None
    source: str = "deterministic"


class TextTurnRequest(BaseModel):
    text: str
    session_id: str | None = None


class ProposedTask(BaseModel):
    title: str
    notes: str | None = None
    due_at: str | None = None
    type: str | None = "task"
    start_time: str | None = None
    end_time: str | None = None
    location: str | None = None
    participants: list[str] | None = None
    estimated_minutes: int | None = 30
    priority: int = 1
    category: str | None = None


class PlanDraftResponse(BaseModel):
    intent: str = "other"
    proposed_tasks: list[ProposedTask] = Field(default_factory=list)
    clarifying_question: str | None = None


class SuggestDayRequest(BaseModel):
    template: str | None = None


class SuggestDayResponse(BaseModel):
    plan_draft: PlanDraftResponse | None = None


class TextTurnResponse(BaseModel):
    reply: str
    assistantMessage: str | None = None
    speak: bool = False
    voiceId: str | None = None
    uiState: str = "idle"
    action: dict | list | str | None = None
    todaySync: dict | list | str | None = None
    crisis: bool = False
    tool_actions: list[str] = Field(default_factory=list)
    session_id: str | None = None
    plan_draft: PlanDraftResponse | None = None


class EmotionResponse(BaseModel):
    emotion: str
    intensity: int = Field(default=1, ge=1, le=10)
    context: str | None = None


class MemoryUsageResponse(BaseModel):
    id: UUID
    title: str
    type: str
    life_area: str | None = None


class SuggestedActionResponse(BaseModel):
    type: str
    label: str
    description: str | None = None
    requires_confirmation: bool = False


class AudioTurnResponse(BaseModel):
    transcript: str
    reply: str
    assistantMessage: str | None = None
    speak: bool = True
    voiceId: str | None = None
    uiState: str = "speaking"
    action: dict | list | str | None = None
    todaySync: dict | list | str | None = None
    crisis: bool = False
    tool_actions: list[str] = Field(default_factory=list)
    session_id: str | None = None
    plan_draft: PlanDraftResponse | None = None
    draft_confirmed: bool = False
    audio_base64: str | None = None
    audio_mime: str | None = None
    mode: str | None = None
    emotion: EmotionResponse | None = None
    memories_used: list[MemoryUsageResponse] = Field(default_factory=list)
    suggested_actions: list[SuggestedActionResponse] = Field(default_factory=list)
    requires_confirmation: bool = False
    confirmation_prompt: str | None = None
    conversation_id: UUID | None = None


class GoalSummaryResponse(BaseModel):
    id: UUID
    title: str
    description: str | None = None
    life_area: str | None = None
    status: str
    priority: str
    target_date: date | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ReflectionSummaryResponse(BaseModel):
    id: UUID
    type: str
    wins: str | None = None
    challenges: str | None = None
    lessons: str | None = None
    mood: str | None = None
    summary: str | None = None
    metadata: dict | list | None = None
    score: dict | list | None = None
    goal_id: UUID | None = None
    created_at: datetime | None = None


class GoalDetailResponse(GoalSummaryResponse):
    linked_tasks: list[TaskResponse] = Field(default_factory=list)
    linked_reflections: list[ReflectionSummaryResponse] = Field(default_factory=list)


class ReflectionDetailResponse(ReflectionSummaryResponse):
    linked_goal: GoalSummaryResponse | None = None


class TaskDetailResponse(TaskResponse):
    linked_goal: GoalSummaryResponse | None = None


class CoachingDecisionRequest(BaseModel):
    question: str
    options: list[str] | None = None


class CoachingDecisionResponse(BaseModel):
    decision_id: UUID
    framework: str
    analysis: dict | list | None = None
    recommendation: str
    confidence: float | None = None
    selected_option: str | None = None


class CoachingDecisionSummary(BaseModel):
    id: UUID
    title: str
    question: str
    options: dict | list | None = None
    selected_option: str | None = None
    framework: str
    analysis: dict | list | None = None
    recommendation: str
    confidence: float | None = None
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class FrameworkRequest(BaseModel):
    framework: str
    prompt: str


class FrameworkResponse(BaseModel):
    framework: str
    output: dict | list | None = None


class FrameworkOption(BaseModel):
    name: str
    description: str


class FrameworkListResponse(BaseModel):
    frameworks: list[FrameworkOption] = Field(default_factory=list)


class GrowthPlanRequest(BaseModel):
    goal_id: UUID | None = None
    horizon: str = "30_day"
    title: str | None = None


class GrowthPlanResponse(BaseModel):
    id: UUID
    goal_id: UUID | None = None
    title: str
    horizon: str
    summary: str | None = None
    milestones: dict | list | None = None
    weekly_focus: dict | list | None = None
    risks: dict | list | None = None
    success_metrics: dict | list | None = None
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class GrowthPlanUpdateRequest(BaseModel):
    title: str | None = None
    summary: str | None = None
    milestones: dict | list | None = None
    weekly_focus: dict | list | None = None
    risks: dict | list | None = None
    success_metrics: dict | list | None = None
    status: str | None = None


class AccountabilitySnapshotRequest(BaseModel):
    period_start: date
    period_end: date


class AccountabilitySnapshotResponse(BaseModel):
    id: UUID
    period_start: date
    period_end: date
    goals_summary: dict | list | None = None
    tasks_summary: dict | list | None = None
    habits_summary: dict | list | None = None
    blockers: dict | list | None = None
    score: float | None = None
    reflection: str | None = None
    created_at: datetime | None = None


class AccountabilityCompareRequest(BaseModel):
    previous_period_start: date
    previous_period_end: date
    current_period_start: date
    current_period_end: date


class HabitCreateRequest(BaseModel):
    name: str
    life_area: str | None = None
    frequency: str = "daily"
    target_count: int = 1


class HabitResponse(BaseModel):
    id: UUID
    name: str
    life_area: str | None = None
    frequency: str
    target_count: int
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class HabitLogRequest(BaseModel):
    value: int = 1
    note: str | None = None
    source: str = "manual"


class HabitLogResponse(BaseModel):
    id: UUID
    habit_id: UUID
    logged_at: datetime
    value: int
    note: str | None = None
    source: str
    created_at: datetime | None = None


class HabitSummaryResponse(BaseModel):
    habits: list[HabitResponse] = Field(default_factory=list)
    streaks: dict[str, int] = Field(default_factory=dict)
    weekly_consistency: dict[str, float] = Field(default_factory=dict)
    suggestions: list[str] = Field(default_factory=list)


class ReminderCreate(BaseModel):
    title: str
    remind_at: datetime
    recurrence_rule: str | None = None
    status: str = "scheduled"
    task_id: int | None = None


class ReminderUpdate(BaseModel):
    title: str | None = None
    remind_at: datetime | None = None
    recurrence_rule: str | None = None
    status: str | None = None
    task_id: int | None = None


class ReminderResponse(BaseModel):
    id: UUID
    user_id: UUID
    task_id: int | None = None
    title: str
    remind_at: datetime
    recurrence_rule: str | None = None
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class NotificationResponse(BaseModel):
    id: UUID
    user_id: UUID
    today_item_id: UUID | None = None
    title: str
    body: str
    type: str
    channel: str
    scheduled_for: datetime | None = None
    sent_at: datetime | None = None
    read_at: datetime | None = None
    status: str = "pending"
    metadata: dict | list | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class NotificationPreferenceResponse(BaseModel):
    in_app_enabled: bool = True
    email_enabled: bool = True
    push_enabled: bool = True
    reminder_lead_minutes: int = 10
    meeting_lead_minutes: int = 30
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None


class NotificationPreferenceUpdate(BaseModel):
    in_app_enabled: bool | None = None
    email_enabled: bool | None = None
    push_enabled: bool | None = None
    reminder_lead_minutes: int | None = Field(default=None, ge=0, le=1440)
    meeting_lead_minutes: int | None = Field(default=None, ge=0, le=1440)
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None


class TaskNudgeResponse(BaseModel):
    text: str
    assistantMessage: str | None = None
    speak: bool = False
    voiceId: str | None = None
    uiState: str = "idle"
    task_id: int
    minutes: int


class TtsRequest(BaseModel):
    text: str
    voice: str | None = None


class TtsResponse(BaseModel):
    text: str
    assistantMessage: str | None = None
    speak: bool = True
    voiceId: str | None = None
    uiState: str = "speaking"
    audio_base64: str | None = None
    audio_mime: str | None = None


class TtsVoiceOption(BaseModel):
    id: str
    name: str
    style: str
    provider: str
    provider_voice_id: str | None = None
    pitch: str | None = None
    rate: str | None = None
    volume: str | None = None
    pause_ms: int | None = None
    warmth: int | None = None
    response_pacing: str | None = None
    preview_text: str | None = None


class GreetingResponse(BaseModel):
    text: str
    assistantMessage: str | None = None
    speak: bool = False
    voiceId: str | None = None
    uiState: str = "listening"
    wake_word_hint: str | None = None
    source: str = "deterministic"


class HealthResponse(BaseModel):
    ok: bool
    version: str = "2.0.0"
    mem0_enabled: bool
    llm_provider: str


class CompanionTurnRequest(BaseModel):
    message: str
    conversation_id: UUID | None = None
    source: str = "text"
    source_context: dict | None = None


class CompanionTurnResponse(BaseModel):
    reply: str
    assistantMessage: str | None = None
    speak: bool = False
    voiceId: str | None = None
    uiState: str = "idle"
    action: dict | list | str | None = None
    todaySync: dict | list | str | None = None
    mode: str
    emotion: EmotionResponse
    memories_used: list[MemoryUsageResponse] = Field(default_factory=list)
    suggested_actions: list[SuggestedActionResponse] = Field(default_factory=list)
    plan_draft: PlanDraftResponse | None = None
    requires_confirmation: bool = False
    confirmation_prompt: str | None = None
    conversation_id: UUID | None = None


class MemoryTimelineItem(BaseModel):
    id: UUID
    date: datetime | None = None
    type: str
    life_area: str | None = None
    title: str
    content: str
    importance: int = 1
    sentiment: str | None = None
    entities: list[str] | None = None
    follow_up_at: datetime | None = None
    follow_up_status: str | None = None
    follow_up_prompt: str | None = None


class MemoryTimelineResponse(BaseModel):
    items: list[MemoryTimelineItem] = Field(default_factory=list)


class FollowUpResponse(BaseModel):
    id: UUID
    title: str
    type: str
    life_area: str | None = None
    prompt: str
    follow_up_at: datetime | None = None
    event_date: datetime | None = None
    follow_up_status: str | None = None
    importance: int = 1
    sentiment: str | None = None
    entities: list[str] | None = None


class LifeAreaInsightItem(BaseModel):
    life_area: str
    memory_count: int = 0
    task_count: int = 0
    goal_count: int = 0
    reflection_count: int = 0
    average_emotion_intensity: float = 0
    balance_score: int = 0


class LifeAreaInsightsResponse(BaseModel):
    areas: list[LifeAreaInsightItem] = Field(default_factory=list)


class WeeklyReviewResponse(BaseModel):
    id: UUID | None = None
    wins: list[str] = Field(default_factory=list)
    challenges: list[str] = Field(default_factory=list)
    lessons: list[str] = Field(default_factory=list)
    mood_trend: dict = Field(default_factory=dict)
    goal_progress: list[dict] = Field(default_factory=list)
    life_area_balance: dict = Field(default_factory=dict)
    recommended_focus: list[str] = Field(default_factory=list)
    summary: str | None = None
    score: dict | list | None = None
    metadata: dict | list | None = None
    created_at: datetime | None = None
    type: str | None = "weekly"


class CompanionScoreResponse(BaseModel):
    overall: int | None = None
    consistency: int | None = None
    energy: int | None = None
    focus: int | None = None
    goal_progress: int | None = None
    reflection_frequency: int | None = None
    explanation: str | None = None
    message: str | None = None


class CompanionPreferenceResponse(BaseModel):
    proactive_enabled: bool = True
    max_proactive_per_day: int = 1
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    tone: str = "warm"
    humor_level: int = 1
    directness_level: int = 5
    voice_pace: str = "normal"
    tts_voice: str = "default"
    voice_profile: str = "calm_female"
    response_length: str = "balanced"


class CompanionPreferenceUpdate(BaseModel):
    proactive_enabled: bool | None = None
    max_proactive_per_day: int | None = None
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    tone: str | None = None
    humor_level: int | None = None
    directness_level: int | None = None
    voice_pace: str | None = None
    tts_voice: str | None = None
    voice_profile: str | None = None
    response_length: str | None = None


class ProactivePromptResponse(BaseModel):
    id: UUID
    trigger_type: str
    prompt: str
    trigger_metadata: dict | list | None = None
    source_type: str | None = None
    source_id: UUID | None = None
    status: str
    priority: int = 5
    scheduled_for: datetime | None = None
    delivered_at: datetime | None = None
    dismissed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProactivePromptGenerateRequest(BaseModel):
    force: bool = False


class EmotionalContinuityItem(BaseModel):
    pattern_type: str
    emotion: str
    life_area: str | None = None
    summary: str
    confidence: float = 0.5
    period_start: date
    period_end: date
    evidence: list[dict] = Field(default_factory=list)


class EmotionalContinuityResponse(BaseModel):
    patterns: list[EmotionalContinuityItem] = Field(default_factory=list)
    summary: str | None = None


class UnderstandingProfileResponse(BaseModel):
    identity_summary: str
    cares_about: list[str] = Field(default_factory=list)
    motivators: list[str] = Field(default_factory=list)
    fears_or_blockers: list[str] = Field(default_factory=list)
    current_builds: list[str] = Field(default_factory=list)
    recurring_patterns: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    growth_edges: list[str] = Field(default_factory=list)


class LifeStoryResponse(BaseModel):
    period: str
    summary: str
    accomplishments: list[str] = Field(default_factory=list)
    patterns: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    growth_summary: list[str] = Field(default_factory=list)


class LifeDashboardResponse(BaseModel):
    goals_progress: list[dict] = Field(default_factory=list)
    mood_trend: dict = Field(default_factory=dict)
    people_mentioned: list[dict] = Field(default_factory=list)
    learning_topics: list[dict] = Field(default_factory=list)
    growth_wins: list[str] = Field(default_factory=list)
    lessons: list[str] = Field(default_factory=list)
    breakthroughs: list[str] = Field(default_factory=list)
    emotional_continuity: EmotionalContinuityResponse | None = None
    companion_score: CompanionScoreResponse | None = None
    proactive_prompts: list[ProactivePromptResponse] = Field(default_factory=list)
    life_area_balance: list[LifeAreaInsightItem] = Field(default_factory=list)


class ConnectedAccountResponse(BaseModel):
    id: UUID
    provider: str
    account_label: str
    scopes: dict | list | None = None
    status: str
    last_sync_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ConnectedAccountCreate(BaseModel):
    provider: str
    account_label: str
    scopes: dict | list | None = None
    status: str = "active"
    access_token: str | None = None
    refresh_token: str | None = None


class ConnectedItemResponse(BaseModel):
    id: UUID
    provider: str
    item_type: str
    external_id: str
    title: str
    content_summary: str | None = None
    source_metadata: dict | list | None = None
    occurred_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ConnectedItemImport(BaseModel):
    connected_account_id: UUID
    provider: str
    item_type: str
    external_id: str
    title: str
    content_summary: str | None = None
    source_metadata: dict | list | None = None
    occurred_at: datetime | None = None


class ExternalCommitmentResponse(BaseModel):
    id: UUID
    source_provider: str
    source_item_id: UUID
    commitment_type: str
    title: str
    due_at: datetime | None = None
    status: str = "open"
    confidence: float = 0.5
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CommitmentCreate(BaseModel):
    title: str
    content: str
    due_at: datetime | None = None
    confidence: float = 0.8
    source_message_id: UUID | None = None
    source_memory_id: UUID | None = None
    follow_up_at: datetime | None = None


class CommitmentUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    due_at: datetime | None = None
    status: str | None = None
    follow_up_at: datetime | None = None
    confidence: float | None = None


class CommitmentResponse(BaseModel):
    id: UUID
    user_id: UUID
    title: str
    content: str
    due_at: datetime | None = None
    status: str = "open"
    source_message_id: UUID | None = None
    source_memory_id: UUID | None = None
    follow_up_at: datetime | None = None
    confidence: float = 0.8
    related_entity_id: UUID | None = None
    related_entity_type: str | None = None
    related_entity_name: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class BusinessProjectResponse(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    status: str = "active"
    goals: dict | list | None = None
    key_people: dict | list | None = None
    risks: dict | list | None = None
    opportunities: dict | list | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class BusinessProjectCreate(BaseModel):
    name: str
    description: str | None = None
    status: str = "active"
    goals: dict | list | None = None
    key_people: dict | list | None = None
    risks: dict | list | None = None
    opportunities: dict | list | None = None


class BusinessProjectEventResponse(BaseModel):
    id: UUID
    project_id: UUID
    event_type: str
    title: str
    description: str | None = None
    occurred_at: datetime | None = None
    source_type: str | None = None
    source_id: UUID | None = None
    created_at: datetime | None = None


def time_to_str(t: time | None) -> str | None:
    return t.strftime("%H:%M") if t else None


def str_to_time(s: str | None) -> time | None:
    if not s:
        return None
    parts = s.split(":")
    return time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
