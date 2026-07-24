from __future__ import annotations

import statistics
import time
import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta

from app.conversation.state import (
    ConversationState,
    PendingAction,
    PendingConfirmation,
    TopicState,
    TopicStatus,
)
from app.conversation.topic_transition import (
    TopicTransitionClassification,
    TopicTransitionService,
    get_topic_classifier,
)
from fixtures.topic_transition_corpus import build_topic_transition_corpus


class _SimilarityClassifier:
    provider = "semantic-test-calibration"
    fallback_active = False

    def __init__(self, active: float, paused: float = 0.0):
        self.active = active
        self.paused = paused

    def similarities(self, utterance: str, candidates: list[str]) -> list[float]:
        paused_count = max(0, len(candidates) - 1)
        return [self.active, *([self.paused] * paused_count), 0.5, 0.5]


def _state(scenario, *, confirmation: bool = False) -> ConversationState:
    user_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    active = TopicState(
        topic_id="active-topic",
        title="Schedule a meeting with Stephen tomorrow",
        active_goal="schedule_meeting",
        entities=dict(scenario.active_entities),
    )
    pending = None
    pending_confirmation = None
    if scenario.pending:
        pending = PendingAction(
            action_id="action-1",
            topic_id=active.topic_id,
            originating_turn_id="turn-previous",
            state="awaiting_confirmation" if confirmation else "awaiting_information",
            kind="meeting",
            intent="create_meeting",
            missing=scenario.missing,
            fields={"person": "Stephen"},
            requires_confirmation=confirmation,
        )
        if confirmation:
            pending_confirmation = PendingConfirmation(
                action_id=pending.action_id,
                topic_id=active.topic_id,
                conversation_id=conversation_id,
                user_id=user_id,
                requested_turn_id="turn-previous",
                prompt="Should I schedule it?",
            )
    history = []
    if scenario.paused_topic:
        history.append(
            TopicState(
                topic_id="qring-topic",
                title="Qring pilot planning and sales rollout",
                active_goal="plan_qring_pilot",
                status=TopicStatus.PAUSED,
            )
        )
    return ConversationState(
        conversation_id=conversation_id,
        user_id=user_id,
        active_topic=active,
        current_topic=active.title,
        topic_history=history,
        pending_action=pending,
        pending_confirmation=pending_confirmation,
    )


def test_topic_transition_corpus_has_required_distribution_and_languages():
    corpus = build_topic_transition_corpus()
    assert len(corpus) == 250
    assert Counter(row.classification for row in corpus) == {
        "continue_same_topic": 40,
        "refine_current_request": 35,
        "modify_active_request": 35,
        "correct_previous_detail": 30,
        "add_related_request": 25,
        "new_related_subtopic": 20,
        "new_unrelated_topic": 25,
        "resume_previous_topic": 20,
        "cancel_active_request": 10,
        "ambiguous_transition": 10,
    }
    assert {row.language for row in corpus} == {"en", "en-NG", "pcm", "en-pcm", "fr"}


def test_topic_transition_corpus_meets_class_specific_thresholds():
    truth = Counter()
    predicted = Counter()
    correct = Counter()
    latencies = []
    unsafe_preservation = 0
    incorrect_cancellation = 0
    for row in build_topic_transition_corpus():
        service = TopicTransitionService(
            _SimilarityClassifier(row.active_similarity, row.paused_similarity)
        )
        state = _state(row)
        decision = service.classify(
            state=state,
            utterance=row.utterance,
            turn_id=row.id,
            language=row.language,
        )
        expected = row.classification
        actual = decision.classification.value
        truth[expected] += 1
        predicted[actual] += 1
        correct[expected] += int(actual == expected)
        latencies.append(decision.classifier_latency_ms)
        policy = service.apply_policy(state, decision, row.utterance, row.language)
        if expected == "new_unrelated_topic" and policy.pending_action is not None:
            unsafe_preservation += 1
        if expected not in {"new_unrelated_topic", "cancel_active_request"} and decision.should_cancel_pending_action:
            incorrect_cancellation += 1

    total = sum(truth.values())
    assert sum(correct.values()) / total >= 0.92
    for label, count in truth.items():
        recall = correct[label] / count
        precision = correct[label] / max(1, predicted[label])
        assert recall >= 0.9, (label, recall)
        if label in {"new_unrelated_topic", "cancel_active_request", "resume_previous_topic"}:
            assert precision >= 0.95, (label, precision)
    assert unsafe_preservation == 0
    assert incorrect_cancellation == 0
    assert statistics.quantiles(latencies, n=20)[18] < 25


def test_confirmation_is_bound_and_stale_confirmation_is_rejected():
    row = next(item for item in build_topic_transition_corpus() if item.pending)
    state = _state(row, confirmation=True)
    service = TopicTransitionService(_SimilarityClassifier(0.9))
    accepted = service.classify(state=state, utterance="Yes", turn_id="confirm", language="en")
    assert accepted.classification == TopicTransitionClassification.CONFIRM_PENDING_ACTION
    rejected_action = service.classify(
        state=state, utterance="No, discard it", turn_id="reject", language="en"
    )
    assert (
        rejected_action.classification
        == TopicTransitionClassification.REJECT_PENDING_ACTION
    )
    stale = state.model_copy(
        update={
            "pending_confirmation": state.pending_confirmation.model_copy(
                update={"topic_id": "other-topic"}
            )
        }
    )
    rejected = service.classify(state=stale, utterance="Yes", turn_id="stale", language="en")
    assert rejected.classification == TopicTransitionClassification.AMBIGUOUS_TRANSITION
    assert rejected.reason_code == "stale_confirmation_rejected"


def test_expired_confirmation_is_not_bound():
    row = next(item for item in build_topic_transition_corpus() if item.pending)
    state = _state(row, confirmation=True)
    state = state.model_copy(
        update={
            "pending_confirmation": state.pending_confirmation.model_copy(
                update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)}
            )
        }
    )
    service = TopicTransitionService(_SimilarityClassifier(0.9))
    assert not service._confirmation_is_bound(state)


def test_stale_topic_sequence_cannot_overwrite_newer_state():
    row = build_topic_transition_corpus()[0]
    state = _state(row).model_copy(update={"topic_transition_sequence": 8, "version": 4})
    decision = TopicTransitionService(_SimilarityClassifier(0.9)).classify(
        state=state, utterance="10:00", turn_id="turn-9", language="en"
    )
    assert decision.transition_sequence == 9
    assert decision.state_version == 4


def test_real_multilingual_classifier_distinguishes_semantics_with_bounded_latency():
    classifier = get_topic_classifier()
    assert classifier.fallback_active is False
    for _ in range(20):
        scores = classifier.similarities(
            "Make it Friday instead",
            ["Schedule a meeting with Stephen tomorrow"],
        )
        assert len(scores) == 3
    summary = classifier.latency_summary()
    assert summary["p95_ms"] is not None
    assert summary["p95_ms"] < 25

    row = build_topic_transition_corpus()[0]
    state = _state(row).model_copy(
        update={
            "active_topic": TopicState(
                topic_id="meeting-query",
                title="What meetings do I have today?",
                active_goal="query_meetings",
            )
        }
    )
    decision = TopicTransitionService(classifier).classify(
        state=state,
        utterance="Create a meeting for today",
        turn_id="new-intent",
        language="en",
    )
    assert decision.classification == TopicTransitionClassification.NEW_RELATED_SUBTOPIC
    assert decision.reason_code == "same_entities_new_intent"


class _SlowSimilarityClassifier(_SimilarityClassifier):
    def similarities(self, utterance: str, candidates: list[str]) -> list[float]:
        time.sleep(0.03)
        return super().similarities(utterance, candidates)


class _TimeoutSimilarityClassifier(_SimilarityClassifier):
    def similarities(self, utterance: str, candidates: list[str]) -> list[float]:
        raise TimeoutError("configured classifier timeout expired")


def test_topic_classifier_timeout_fails_safe_without_cancelling_pending_action():
    row = next(item for item in build_topic_transition_corpus() if item.pending)
    state = _state(row)
    service = TopicTransitionService(_TimeoutSimilarityClassifier(0.9))
    decision = service.classify(
        state=state,
        utterance="Change it",
        turn_id="timeout-turn",
        language="en",
    )
    policy = service.apply_policy(state, decision, "Change it", "en")
    assert decision.classification == TopicTransitionClassification.AMBIGUOUS_TRANSITION
    assert decision.reason_code == "classifier_timeout"
    assert decision.requires_clarification is True
    assert policy.pending_action is not None


def test_slow_completed_topic_classifier_keeps_semantic_decision():
    row = build_topic_transition_corpus()[0]
    state = _state(row)
    service = TopicTransitionService(_SlowSimilarityClassifier(0.9))
    decision = service.classify(
        state=state,
        utterance="Change it to Friday",
        turn_id="slow-complete-turn",
        language="en",
    )
    assert decision.classification != TopicTransitionClassification.AMBIGUOUS_TRANSITION
    assert decision.reason_code != "classifier_timeout"
