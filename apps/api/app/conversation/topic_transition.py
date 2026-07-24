"""Semantic topic transitions and backend-authoritative state policy."""

from __future__ import annotations

import logging
import re
import threading
import time
import warnings
from collections import Counter, deque
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from ..config import get_settings
from .state import ConversationState, PendingAction, TopicState, TopicStatus

log = logging.getLogger("aipal.topic_transition")
_WORD = re.compile(r"[\w'-]+", re.UNICODE)
_TIME = re.compile(r"\b(?:[01]?\d|2[0-3])(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?|h)?\b", re.I)
_DATE = re.compile(
    r"\b(?:today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"aujourd'hui|demain|lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\b",
    re.I,
)


class TopicTransitionClassification(StrEnum):
    CONTINUE_SAME_TOPIC = "continue_same_topic"
    REFINE_CURRENT_REQUEST = "refine_current_request"
    MODIFY_ACTIVE_REQUEST = "modify_active_request"
    CORRECT_PREVIOUS_DETAIL = "correct_previous_detail"
    ADD_RELATED_REQUEST = "add_related_request"
    NEW_RELATED_SUBTOPIC = "new_related_subtopic"
    NEW_UNRELATED_TOPIC = "new_unrelated_topic"
    RESUME_PREVIOUS_TOPIC = "resume_previous_topic"
    CANCEL_ACTIVE_REQUEST = "cancel_active_request"
    REJECT_PENDING_ACTION = "reject_pending_action"
    CONFIRM_PENDING_ACTION = "confirm_pending_action"
    AMBIGUOUS_TRANSITION = "ambiguous_transition"


class TopicTransitionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    classification: TopicTransitionClassification
    confidence: float = Field(ge=0, le=1)
    reason_code: str
    current_topic_id: str | None = None
    previous_topic_id: str | None = None
    target_topic_id: str | None = None
    active_goal: str | None = None
    related_intent: str | None = None
    should_preserve_context: bool = True
    should_preserve_pending_action: bool = True
    should_cancel_pending_action: bool = False
    should_start_new_topic: bool = False
    should_resume_previous_topic: bool = False
    requires_clarification: bool = False
    entities_added: list[str] = Field(default_factory=list)
    entities_replaced: dict[str, Any] = Field(default_factory=dict)
    model_version: str = "topic-transition-v1"
    transition_sequence: int = Field(default=0, ge=0)
    state_version: int = Field(default=1, ge=1)
    turn_id: str
    pending_action_id: str | None = None
    fallback_reason: str | None = None
    classifier_latency_ms: float = Field(default=0, ge=0)


@dataclass(frozen=True, slots=True)
class TopicPolicyResult:
    decision: TopicTransitionDecision
    active_topic: TopicState
    topic_history: tuple[TopicState, ...]
    pending_action: PendingAction | None
    clear_pending_confirmation: bool


class SemanticTopicClassifier:
    provider = "semantic-local"
    model_version = "topic-transition-v1"
    fallback_active = False
    _MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    def __init__(self) -> None:
        from fastembed import TextEmbedding

        settings = get_settings()
        started = time.perf_counter()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            self._embedder = TextEmbedding(
                settings.topic_classifier_model,
                cache_dir=settings.semantic_endpointing_model_cache_path,
            )
            intent_vectors = np.asarray(
                list(
                    self._embedder.embed(
                        [
                            "asking to view or explain existing information",
                            "requesting creation or modification of an action",
                        ]
                    )
                ),
                dtype=np.float32,
            )
        self._intent_vectors = intent_vectors / np.maximum(
            np.linalg.norm(intent_vectors, axis=1, keepdims=True), 1e-9
        )
        self._candidate_vectors: dict[str, np.ndarray] = {}
        self.preload_ms = round((time.perf_counter() - started) * 1000, 3)
        self._latencies: deque[float] = deque(maxlen=512)
        self._lock = threading.RLock()

    @property
    def model_name(self) -> str:
        return self._MODEL

    def similarities(self, utterance: str, candidates: list[str]) -> list[float]:
        started = time.perf_counter()
        with self._lock:
            utterance_vector = np.asarray(
                next(self._embedder.embed([utterance])), dtype=np.float32
            )
            utterance_vector /= max(float(np.linalg.norm(utterance_vector)), 1e-9)
            candidate_vectors = []
            for candidate in candidates:
                vector = self._candidate_vectors.get(candidate)
                if vector is None:
                    vector = np.asarray(
                        next(self._embedder.embed([candidate])), dtype=np.float32
                    )
                    vector /= max(float(np.linalg.norm(vector)), 1e-9)
                    if len(self._candidate_vectors) >= 128:
                        self._candidate_vectors.pop(next(iter(self._candidate_vectors)))
                    self._candidate_vectors[candidate] = vector
                candidate_vectors.append(vector)
            scores = np.asarray(candidate_vectors) @ utterance_vector
            intent_scores = self._intent_vectors @ utterance_vector
        self._latencies.append((time.perf_counter() - started) * 1000)
        return [
            *[float(value) for value in scores],
            *[float(value) for value in intent_scores],
        ]

    def latency_summary(self) -> dict[str, float | None]:
        if not self._latencies:
            return {"median_ms": None, "p95_ms": None}
        return {
            "median_ms": round(float(np.median(self._latencies)), 3),
            "p95_ms": round(float(np.percentile(self._latencies, 95)), 3),
        }


class AmbiguousTopicClassifier:
    provider = "safe-ambiguous-fallback"
    model_version = "topic-transition-v1"
    fallback_active = True
    preload_ms = 0.0

    @property
    def model_name(self) -> str:
        return get_settings().topic_classifier_model

    def similarities(self, utterance: str, candidates: list[str]) -> list[float]:
        raise RuntimeError("semantic topic model unavailable")

    def latency_summary(self) -> dict[str, float | None]:
        return {"median_ms": None, "p95_ms": None}


@lru_cache(maxsize=1)
def get_topic_classifier() -> SemanticTopicClassifier | AmbiguousTopicClassifier:
    settings = get_settings()
    if settings.topic_classifier_provider == "semantic_local":
        try:
            return SemanticTopicClassifier()
        except Exception:
            if settings.topic_classifier_fallback_mode == "disabled":
                raise
            log.exception("semantic_topic_model_initialization_failed")
            return AmbiguousTopicClassifier()
    if settings.topic_classifier_provider == "ambiguous_fallback":
        return AmbiguousTopicClassifier()
    raise ValueError(f"Unsupported topic classifier: {settings.topic_classifier_provider}")


class TopicTransitionService:
    _CANCEL = re.compile(r"^(?:cancel|stop|never mind|leave am|annule|laisse tomber)\b", re.I)
    _CONFIRM = re.compile(r"^(?:yes|yeah|confirm|go ahead|do it|oui|yes abeg)\b", re.I)
    _REJECT = re.compile(r"^(?:no|nope|reject|don't|do not|non|cancel am)\b", re.I)
    _CONTINUE = re.compile(r"^(?:continue|continue that|same topic|go on|carry on)\b", re.I)
    _RESUME = re.compile(r"\b(?:back to|return to|continue with|go back|make we go back|revenons à)\b", re.I)
    _CORRECT = re.compile(r"\b(?:sorry|actually|i meant|make that|rather|no,|désolé|plutôt|je voulais dire)\b", re.I)
    _MULTI = re.compile(r"\b(?:and also|also remind|and remind|plus|et aussi)\b", re.I)

    def __init__(self, classifier: Any | None = None) -> None:
        self.classifier = classifier or get_topic_classifier()
        self._counts: Counter[str] = Counter()

    def classify(
        self,
        *,
        state: ConversationState,
        utterance: str,
        turn_id: str,
        language: str = "unknown",
    ) -> TopicTransitionDecision:
        started = time.perf_counter()
        active = state.active_topic
        sequence = state.topic_transition_sequence + 1
        pending = state.pending_action
        base = dict(
            current_topic_id=active.topic_id if active else None,
            previous_topic_id=active.topic_id if active else None,
            target_topic_id=active.topic_id if active else None,
            active_goal=active.active_goal if active else None,
            transition_sequence=sequence,
            state_version=state.version,
            turn_id=turn_id,
            pending_action_id=pending.action_id if pending else None,
        )

        def decision(classification: TopicTransitionClassification, confidence: float, reason: str, **values: Any) -> TopicTransitionDecision:
            payload = {**base, **values}
            payload["classifier_latency_ms"] = (time.perf_counter() - started) * 1000
            result = TopicTransitionDecision(
                classification=classification,
                confidence=confidence,
                reason_code=reason,
                **payload,
            )
            self._counts[result.classification.value] += 1
            return result

        clean = utterance.strip()
        processed_turns = list(state.metadata.get("processed_topic_turn_ids") or [])
        if turn_id in processed_turns:
            return decision(
                TopicTransitionClassification.AMBIGUOUS_TRANSITION,
                1.0,
                "duplicate_user_event_rejected",
                requires_clarification=False,
            )
        if active and self._CANCEL.search(clean):
            return decision(TopicTransitionClassification.CANCEL_ACTIVE_REQUEST, 0.995, "explicit_cancel", should_preserve_context=False, should_preserve_pending_action=False, should_cancel_pending_action=True)
        if pending and state.pending_confirmation and self._CONFIRM.search(clean):
            bound = self._confirmation_is_bound(state)
            if bound:
                return decision(TopicTransitionClassification.CONFIRM_PENDING_ACTION, 0.995, "bound_confirmation", related_intent=pending.intent)
            return decision(TopicTransitionClassification.AMBIGUOUS_TRANSITION, 0.99, "stale_confirmation_rejected", requires_clarification=True, should_preserve_pending_action=False)
        if pending and state.pending_confirmation and self._REJECT.search(clean):
            return decision(TopicTransitionClassification.REJECT_PENDING_ACTION, 0.995, "bound_rejection", should_preserve_pending_action=False, should_cancel_pending_action=True)
        if not active:
            return decision(TopicTransitionClassification.NEW_UNRELATED_TOPIC, 0.99, "first_topic", should_start_new_topic=True, should_preserve_context=False, target_topic_id=None)
        if self._CONTINUE.search(clean):
            return decision(
                TopicTransitionClassification.CONTINUE_SAME_TOPIC,
                0.97,
                "explicit_continue",
            )

        paused = [topic for topic in state.topic_history if topic.status == TopicStatus.PAUSED][: get_settings().topic_classifier_max_paused_topics]
        candidates = [
            active.title,
            *[topic.title for topic in paused],
        ]
        try:
            scores = self.classifier.similarities(clean, candidates)
        except TimeoutError:
            return decision(TopicTransitionClassification.AMBIGUOUS_TRANSITION, 0.0, "classifier_timeout", requires_clarification=True, fallback_reason="classifier_timeout")
        except Exception as exc:
            return decision(TopicTransitionClassification.AMBIGUOUS_TRANSITION, 0.0, "classifier_unavailable", requires_clarification=True, fallback_reason=type(exc).__name__)
        elapsed_ms = (time.perf_counter() - started) * 1000
        latency_slo_ms = get_settings().topic_classifier_latency_slo_seconds * 1000
        if elapsed_ms > latency_slo_ms:
            log.warning(
                "topic_classifier_latency_exceeded_slo latency_ms=%.3f slo_ms=%.3f",
                elapsed_ms,
                latency_slo_ms,
            )
        active_similarity = scores[0]
        paused_scores = scores[1 : 1 + len(paused)]
        best_paused_index = int(np.argmax(paused_scores)) if paused_scores else -1
        paused_similarity = scores[best_paused_index + 1] if best_paused_index >= 0 else 0.0
        query_intent_score, mutation_intent_score = scores[-2:]
        entities = self._entities(clean)
        replaced = {
            key: value
            for key, value in entities.items()
            if key in active.entities and active.entities[key] != value
        }
        added = [value for key, value in entities.items() if key not in active.entities]

        if self._RESUME.search(clean) and best_paused_index >= 0 and paused_similarity >= get_settings().topic_classifier_resume_similarity:
            target = paused[best_paused_index]
            return decision(TopicTransitionClassification.RESUME_PREVIOUS_TOPIC, min(0.99, paused_similarity + 0.2), "explicit_semantic_resume", target_topic_id=target.topic_id, should_resume_previous_topic=True, should_preserve_pending_action=False)
        if self._CORRECT.search(clean) and (replaced or active_similarity >= 0.35):
            return decision(TopicTransitionClassification.CORRECT_PREVIOUS_DETAIL, 0.96, "correction_replaces_entity", entities_replaced=replaced, entities_added=added)
        if pending and replaced:
            return decision(TopicTransitionClassification.MODIFY_ACTIVE_REQUEST, 0.95, "pending_action_entity_changed", entities_replaced=replaced, entities_added=added)
        if self._MULTI.search(clean):
            return decision(TopicTransitionClassification.ADD_RELATED_REQUEST, 0.94, "related_multi_intent", entities_added=added)
        if (
            active.active_goal
            and any(marker in active.active_goal for marker in ("query", "view", "list"))
            and mutation_intent_score > query_intent_score + 0.08
        ):
            return decision(
                TopicTransitionClassification.NEW_RELATED_SUBTOPIC,
                min(0.95, mutation_intent_score + 0.15),
                "same_entities_new_intent",
                should_start_new_topic=True,
                should_preserve_pending_action=False,
            )
        if self._answers_missing_information(state, clean):
            return decision(TopicTransitionClassification.CONTINUE_SAME_TOPIC, 0.96, "answers_requested_information", entities_added=added)
        settings = get_settings()
        if active_similarity >= settings.topic_classifier_same_topic_similarity:
            classification = TopicTransitionClassification.REFINE_CURRENT_REQUEST if replaced or added else TopicTransitionClassification.CONTINUE_SAME_TOPIC
            return decision(classification, min(0.98, active_similarity + 0.15), "semantic_same_topic", entities_replaced=replaced, entities_added=added)
        if paused_similarity >= settings.topic_classifier_resume_similarity and paused_similarity > active_similarity + 0.12:
            return decision(TopicTransitionClassification.RESUME_PREVIOUS_TOPIC, min(0.96, paused_similarity + 0.1), "semantic_topic_return", target_topic_id=paused[best_paused_index].topic_id, should_resume_previous_topic=True, should_preserve_pending_action=False)
        if active_similarity >= settings.topic_classifier_related_similarity:
            return decision(TopicTransitionClassification.NEW_RELATED_SUBTOPIC, min(0.92, active_similarity + 0.12), "semantic_related_subtopic", should_start_new_topic=True, should_preserve_pending_action=False)
        if active_similarity <= settings.topic_classifier_unrelated_similarity:
            return decision(TopicTransitionClassification.NEW_UNRELATED_TOPIC, min(0.99, 1.0 - active_similarity), "semantic_unrelated_topic", should_preserve_context=False, should_preserve_pending_action=False, should_cancel_pending_action=pending is not None, should_start_new_topic=True, target_topic_id=None)
        return decision(TopicTransitionClassification.AMBIGUOUS_TRANSITION, 0.5, "semantic_margin_ambiguous", requires_clarification=True)

    def apply_policy(self, state: ConversationState, decision: TopicTransitionDecision, utterance: str, language: str) -> TopicPolicyResult:
        had_active_topic = state.active_topic is not None
        active = state.active_topic or self._new_topic(utterance, decision.turn_id, language)
        history = list(state.topic_history)
        pending = state.pending_action
        clear_confirmation = False
        classification = decision.classification
        if classification == TopicTransitionClassification.RESUME_PREVIOUS_TOPIC:
            target = next((topic for topic in history if topic.topic_id == decision.target_topic_id and topic.status != TopicStatus.CANCELLED), None)
            if target is None:
                decision = decision.model_copy(update={"classification": TopicTransitionClassification.AMBIGUOUS_TRANSITION, "reason_code": "resume_target_invalid", "requires_clarification": True})
            else:
                history = [topic.model_copy(update={"status": TopicStatus.PAUSED}) if topic.topic_id == active.topic_id else topic for topic in history]
                active = target.model_copy(update={"status": TopicStatus.ACTIVE, "resume_count": target.resume_count + 1, "updated_at": self._now(), "last_turn_id": decision.turn_id, "pending_action_id": None})
                pending = None
                clear_confirmation = True
        elif classification in {TopicTransitionClassification.NEW_UNRELATED_TOPIC, TopicTransitionClassification.NEW_RELATED_SUBTOPIC} and not had_active_topic:
            pass
        elif classification in {TopicTransitionClassification.NEW_UNRELATED_TOPIC, TopicTransitionClassification.NEW_RELATED_SUBTOPIC}:
            old = active.model_copy(update={"status": TopicStatus.PAUSED, "updated_at": self._now()})
            history = self._bounded_history([old, *history])
            active = self._new_topic(utterance, decision.turn_id, language, parent_topic_id=old.topic_id if classification == TopicTransitionClassification.NEW_RELATED_SUBTOPIC else None)
            pending = None
            clear_confirmation = True
        elif classification == TopicTransitionClassification.CANCEL_ACTIVE_REQUEST:
            active = active.model_copy(update={"status": TopicStatus.CANCELLED, "updated_at": self._now(), "last_turn_id": decision.turn_id, "pending_action_id": None})
            pending = None
            clear_confirmation = True
        elif classification == TopicTransitionClassification.REJECT_PENDING_ACTION:
            pending = None
            clear_confirmation = True
            active = active.model_copy(update={"status": TopicStatus.ACTIVE, "pending_action_id": None, "updated_at": self._now()})
        elif classification == TopicTransitionClassification.AMBIGUOUS_TRANSITION:
            pass
        else:
            entities = dict(active.entities)
            entities.update(self._entities(utterance))
            active = active.model_copy(update={"entities": entities, "updated_at": self._now(), "last_turn_id": decision.turn_id, "language": language or active.language})
        return TopicPolicyResult(decision=decision, active_topic=active, topic_history=tuple(self._bounded_history(history)), pending_action=pending, clear_pending_confirmation=clear_confirmation)

    @staticmethod
    def _confirmation_is_bound(state: ConversationState) -> bool:
        from datetime import UTC, datetime

        confirmation = state.pending_confirmation
        pending = state.pending_action
        active = state.active_topic
        return bool(
            confirmation
            and pending
            and active
            and confirmation.invalidated_at is None
            and confirmation.expires_at > datetime.now(UTC)
            and pending.expires_at > datetime.now(UTC)
            and confirmation.action_id == pending.action_id
            and confirmation.topic_id == active.topic_id
            and confirmation.conversation_id == state.conversation_id
            and confirmation.user_id == state.user_id
        )

    @staticmethod
    def _answers_missing_information(state: ConversationState, text: str) -> bool:
        pending = state.pending_action
        if not pending or not pending.missing:
            return False
        return bool(_TIME.search(text) or _DATE.search(text) or len(_WORD.findall(text)) <= 5)

    @staticmethod
    def _entities(text: str) -> dict[str, str]:
        entities: dict[str, str] = {}
        if match := _TIME.search(text):
            entities["time"] = match.group(0)
        if match := _DATE.search(text):
            entities["date"] = match.group(0)
        return entities

    @staticmethod
    def _new_topic(text: str, turn_id: str, language: str, parent_topic_id: str | None = None) -> TopicState:
        return TopicState(title=text[:240] or "Conversation topic", last_turn_id=turn_id, language=language or "unknown", entities=TopicTransitionService._entities(text), parent_topic_id=parent_topic_id)

    @staticmethod
    def _bounded_history(topics: list[TopicState]) -> list[TopicState]:
        unique: dict[str, TopicState] = {}
        for topic in topics:
            unique.setdefault(topic.topic_id, topic)
        return list(unique.values())[:20]

    @staticmethod
    def _now():
        from datetime import UTC, datetime

        return datetime.now(UTC)


topic_transition_service = TopicTransitionService()
