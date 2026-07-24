"""Server-authoritative neural and semantic turn detection."""

from __future__ import annotations

import logging
import hashlib
import math
import re
import threading
import time
import warnings
from collections import Counter, deque
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import StrEnum
from functools import lru_cache
from typing import Any, Protocol

import numpy as np

from ..config import get_settings

log = logging.getLogger("aipal.turn_detection")

SAMPLE_RATE = 16_000
SAMPLE_WIDTH_BYTES = 2
_WORD = re.compile(r"[\w']+", re.UNICODE)
_INCOMPLETE_TAILS = frozenset(
    {
        "and",
        "because",
        "but",
        "for",
        "if",
        "or",
        "so",
        "that",
        "then",
        "to",
        "when",
        "while",
        "with",
    }
)
_SHORT_COMMANDS = frozenset(
    {"stop", "cancel", "yes", "no", "confirm", "continue", "pause", "resume"}
)
_CORRECTION_MARKERS = (
    "actually",
    "i mean",
    "make that",
    "rather",
    "sorry",
    "correction",
)
_THINKING_MARKERS = (
    "give me a second",
    "let me think",
    "one moment",
    "hold on",
    "wait",
)
_DATE_OR_TIME_HINT = re.compile(
    r"\b(\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)?|today|tomorrow|yesterday|"
    r"next\s+week|monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"demain|matin|soir|lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\b",
    re.IGNORECASE,
)
_CORRECTION_TAIL = re.compile(r"(?:\.\.\.|…|,\s*)$")
_LIST_TAIL = re.compile(r"(?:,|and|et|and\s+|na\s+|plus|plus\s+)$", re.IGNORECASE)
_MODEL_VERSION = "endpoint-v2"
_SEMANTIC_VECTOR_SIZE = 48


def _normalize_language(language: str | None) -> str:
    value = str(language or "").strip().casefold().replace("_", "-")
    if not value:
        return "unknown"
    return value.split("-", 1)[0] or "unknown"


def _language_primary_subtag(language: str | None) -> str:
    value = _normalize_language(language)
    if value == "unknown":
        return value
    return value.split("-", 1)[0] or "unknown"


def _token_shape(token: str) -> str:
    if not token:
        return "empty"
    if token.isdigit():
        return "digit"
    if token.replace(".", "", 1).isdigit():
        return "numeric"
    if token.isalpha() and token.isupper():
        return "upper"
    if token.isalpha() and token[:1].isupper():
        return "title"
    if token.isalpha():
        return "alpha"
    return "mixed"


def _semantic_vector(text: str) -> list[float]:
    folded = re.sub(r"\s+", " ", (text or "").casefold()).strip()
    if not folded:
        return [0.0] * _SEMANTIC_VECTOR_SIZE
    vector = [0.0] * _SEMANTIC_VECTOR_SIZE
    words = _WORD.findall(folded)
    for index, token in enumerate(words):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % _SEMANTIC_VECTOR_SIZE
        vector[bucket] += 1.0 + (index % 3) * 0.05
    padded = f"  {folded}  "
    for offset in range(max(0, len(padded) - 2)):
        gram = padded[offset : offset + 3]
        digest = hashlib.sha256(gram.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[4:8], "big") % _SEMANTIC_VECTOR_SIZE
        vector[bucket] += 0.35
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def _semantic_similarity(left: str, right: str) -> float:
    left_vec = _semantic_vector(left)
    right_vec = _semantic_vector(right)
    similarity = sum(
        left_value * right_value
        for left_value, right_value in zip(left_vec, right_vec, strict=False)
    )
    return max(0.0, min(1.0, similarity))


def _probability_bucket(value: float | None, *, scale: int = 10) -> str:
    if value is None:
        return "none"
    bounded = max(0.0, min(1.0, float(value)))
    return str(int(round(bounded * scale)))


def _hash_bucket(value: str, *, modulo: int = 16) -> str:
    if not value:
        return "none"
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return str(int.from_bytes(digest[:2], "big") % modulo)


class EndpointDecision(StrEnum):
    CONTINUE_LISTENING = "continue_listening"
    LIKELY_COMPLETE = "likely_complete"
    FORCE_COMPLETE = "force_complete"
    UNCERTAIN = "uncertain"


class TurnSignal(StrEnum):
    SPEECH_STARTED = "speech_started"
    SPEECH_RESUMED = "speech_resumed"
    THINKING_PAUSE = "thinking_pause"
    ENDPOINT = "endpoint"


class PauseKind(StrEnum):
    THINKING = "thinking"
    FINISHED = "finished"
    INTERRUPTED = "interrupted"
    TOPIC_CHANGE = "topic_change"


class AcousticState(StrEnum):
    SILENCE = "silence"
    POSSIBLE_SPEECH = "possible_speech"
    SPEECH_STARTED = "speech_started"
    SPEECH_ACTIVE = "speech_active"
    TEMPORARY_PAUSE = "temporary_pause"
    THINKING_PAUSE = "thinking_pause"
    SPEECH_ENDED = "speech_ended"
    BARGE_IN = "barge_in"
    PROBABLE_ECHO = "probable_echo"
    PROBABLE_NOISE = "probable_noise"
    FORCED_ENDPOINT = "forced_endpoint"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True, slots=True)
class AcousticTurnDecision:
    state: AcousticState
    confidence: float
    reason: str
    speech_probability: float
    silence_ms: int
    utterance_ms: int
    ai_speaking: bool
    provider: str

    def to_transport(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "confidence": round(self.confidence, 4),
            "reason": self.reason,
            "speech_probability": round(self.speech_probability, 4),
            "silence_ms": self.silence_ms,
            "utterance_ms": self.utterance_ms,
            "ai_speaking": self.ai_speaking,
            "provider": self.provider,
        }


@dataclass(frozen=True, slots=True)
class EndpointContext:
    current_topic: str | None = None
    current_goal: str | None = None
    current_intent: str | None = None
    pending_action: dict[str, Any] | None = None
    missing_slots: tuple[str, ...] = ()
    conversation_locale: str | None = None
    user_language_preference: str | None = None
    detected_language: str | None = None
    language_confidence: float | None = None
    languages: tuple[str, ...] = ()
    code_switching_detected: bool = False
    previous_transcript: str | None = None


@dataclass(frozen=True, slots=True)
class SemanticClassScores:
    label: str
    confidence: float
    scores: dict[str, float]
    provider: str
    fallback_active: bool = False


@dataclass(frozen=True, slots=True)
class SemanticEndpointDecision:
    decision: EndpointDecision
    confidence: float
    reason: str
    recommended_wait_ms: int
    completion_probability: float
    classifier_label: str
    classifier_provider: str
    classifier_latency_ms: float
    model_version: str = "endpoint-v2"
    required_slots_remaining: tuple[str, ...] = ()
    transcript_stability: float = 0.0
    recent_change_ratio: float = 0.0
    detected_language: str = "unknown"
    language_confidence: float = 0.0
    code_switching_detected: bool = False
    languages: tuple[str, ...] = ()
    language_support_mode: str = "language-agnostic fallback active"
    fallback_reason: str | None = None

    def to_transport(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "confidence": self.confidence,
            "reason": self.reason,
            "recommended_wait_ms": self.recommended_wait_ms,
            "completion_probability": self.completion_probability,
            "classifier_label": self.classifier_label,
            "classifier_provider": self.classifier_provider,
            "model_version": self.model_version,
            "classifier_latency_ms": round(self.classifier_latency_ms, 3),
            "required_slots_remaining": list(self.required_slots_remaining),
            "transcript_stability": self.transcript_stability,
            "recent_change_ratio": self.recent_change_ratio,
            "detected_language": self.detected_language,
            "language_confidence": self.language_confidence,
            "code_switching_detected": self.code_switching_detected,
            "languages": list(self.languages),
            "language_support_mode": self.language_support_mode,
            "fallback_reason": self.fallback_reason,
        }


@dataclass(frozen=True, slots=True)
class TurnDetectionEvent:
    signal: TurnSignal
    speech_probability: float
    audio_ms: int
    silence_ms: int = 0
    completion_probability: float = 0.0
    pause_kind: PauseKind | None = None
    reason: str | None = None
    preroll_pcm: bytes = b""
    endpoint_decision: SemanticEndpointDecision | None = None
    acoustic_decision: AcousticTurnDecision | None = None


class SpeechProbabilityProvider(Protocol):
    name: str
    fallback_active: bool

    def score(self, pcm: bytes) -> float: ...
    def reset(self) -> None: ...
    def diagnostics(self) -> dict[str, Any]: ...


class SemanticEndpointClassifier(Protocol):
    name: str
    fallback_active: bool

    def classify(self, text: str, context: EndpointContext) -> SemanticClassScores: ...


class SileroSpeechProbability:
    """Rolling-window Silero v6 inference using Faster-Whisper's bundled model."""

    name = "silero_v6"
    fallback_active = False
    model_source = "faster-whisper bundled ONNX"

    def __init__(self, *, window_samples: int = 4_096) -> None:
        from faster_whisper.vad import get_vad_model

        self._model = get_vad_model()
        self._window_samples = max(512, window_samples // 512 * 512)
        self._samples = np.zeros(0, dtype=np.float32)
        self._lock = threading.Lock()
        self._latencies_ms: deque[float] = deque(maxlen=512)
        self._inferences = 0

    def score(self, pcm: bytes) -> float:
        if not pcm:
            return 0.0
        samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32_768.0
        self._samples = np.concatenate((self._samples, samples))[
            -self._window_samples :
        ]
        usable = self._samples.size // 512 * 512
        if usable == 0:
            return 0.0
        window = self._samples[-usable:]
        started = time.perf_counter()
        with self._lock:
            probabilities = self._model(window)
        self._latencies_ms.append((time.perf_counter() - started) * 1_000)
        self._inferences += 1
        return max(0.0, min(1.0, float(np.asarray(probabilities).reshape(-1)[-1])))

    def reset(self) -> None:
        self._samples = np.zeros(0, dtype=np.float32)

    def diagnostics(self) -> dict[str, Any]:
        values = sorted(self._latencies_ms)
        def percentile(q: float) -> float | None:
            if not values:
                return None
            return values[min(len(values) - 1, int((len(values) - 1) * q))]
        settings = get_settings()
        return {
            "provider": self.name,
            "model": "Silero VAD",
            "version": settings.neural_vad_model_version,
            "source": self.model_source,
            "device": settings.neural_vad_device,
            "sample_rate": SAMPLE_RATE,
            "fallback_active": False,
            "healthy": True,
            "inferences": self._inferences,
            "latency_median_ms": percentile(0.5),
            "latency_p95_ms": percentile(0.95),
        }


class AdaptiveEnergyProbability:
    """Calibrated fallback used only when the neural runtime cannot initialize."""

    name = "adaptive_energy_fallback"
    fallback_active = True

    def __init__(self) -> None:
        self._noise_rms = 0.008

    def score(self, pcm: bytes) -> float:
        if not pcm:
            return 0.0
        samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32_768.0
        rms = float(np.sqrt(np.mean(np.square(samples)))) if samples.size else 0.0
        ratio = rms / max(0.001, self._noise_rms)
        probability = 1.0 / (1.0 + math.exp(-3.2 * (ratio - 2.2)))
        if probability < 0.2:
            self._noise_rms = 0.98 * self._noise_rms + 0.02 * max(rms, 0.0005)
        return max(0.0, min(1.0, probability))

    def reset(self) -> None:
        self._noise_rms = 0.008

    def diagnostics(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "model": "adaptive RMS energy",
            "version": "energy-v1",
            "source": "internal deterministic fallback",
            "device": "cpu",
            "sample_rate": SAMPLE_RATE,
            "fallback_active": True,
            "healthy": True,
            "latency_median_ms": None,
            "latency_p95_ms": None,
        }


def create_speech_probability_provider() -> SpeechProbabilityProvider:
    settings = get_settings()
    try:
        if settings.neural_vad_provider != "silero_v6":
            raise RuntimeError(f"unsupported neural VAD provider: {settings.neural_vad_provider}")
        return SileroSpeechProbability()
    except Exception:
        log.exception(
            "silero_vad_initialization_failed; using adaptive energy fallback"
        )
        if (
            settings.aipal_env.lower() in {"production", "prod"}
            and settings.neural_vad_production_fallback_policy == "fail_closed"
        ):
            raise RuntimeError("Neural VAD is required in production")
        return AdaptiveEnergyProbability()


class LocalStatisticalEndpointClassifier:
    """Bounded multinomial classifier trained from endpointing utterance fixtures."""

    name = "local_statistical_endpoint_v1"
    fallback_active = False
    model_version = _MODEL_VERSION
    model_size = "small-local-hybrid"
    _TRAINING = {
        "complete_command": (
            "stop",
            "cancel that",
            "pause playback",
            "schedule a meeting with Stephen tomorrow at ten",
            "book a meeting with Kelvin on Friday at three",
            "remind me to call Stephen tomorrow",
            "add soap to my shopping list",
            "show my calendar",
            "make it Friday morning",
            "stop am",
            "cancel am",
            "jowo se ipinnu meeting na for Friday",
            "planifie la reunion avec Awa demain",
            "arrete la lecture",
        ),
        "complete_question": (
            "what do I have today",
            "when is my next meeting",
            "can you show my tasks",
            "who am I meeting tomorrow",
            "what should I do first",
            "ki ni mo ni loni",
            "na when be my next meeting",
            "quand est mon prochain rendez vous",
            "quand est la reunion",
        ),
        "incomplete_request": (
            "schedule a meeting with Stephen",
            "schedule a meeting",
            "remind me to call",
            "I want to",
            "the meeting is at",
            "book a call with",
            "add this to",
            "make am for",
            "remind me say",
            "planifie avec",
            "make we",
            "demain a",
        ),
        "thinking_continuation": (
            "give me a second I am still thinking",
            "let me think before I finish",
            "hold on I have not finished",
            "the meeting is at give me a second",
            "wait one moment",
            "one minute make I think",
            "attends un moment",
            "make I think small",
            "laisse-moi reflechir",
        ),
        "list_continuation": (
            "add milk bread eggs and",
            "the list includes milk bread and",
            "first this then that and one more",
            "add these items milk bread eggs",
            "add akara, moi moi, and",
            "ajoute pain beurre et",
            "put rice, beans, and",
            "ajoute pain, beurre, et",
        ),
        "correction": (
            "actually make that Friday",
            "I mean tomorrow at three",
            "sorry correct the date to Monday",
            "no change it to ten",
            "rather make it next week",
            "na Tuesday no Friday",
            "non plutot demain matin",
            "no make it Friday",
            "non, plutot vendredi",
        ),
        "confirmation": (
            "yes",
            "no",
            "confirm it",
            "go ahead",
            "do it",
            "cancel it",
            "oui",
            "non",
            "abeg",
            "leave am",
        ),
    }

    def __init__(self) -> None:
        self._created_at = time.perf_counter()
        self._label_counts: dict[str, Counter[str]] = {}
        self._label_totals: dict[str, int] = {}
        vocabulary: set[str] = set()
        total_examples = sum(len(rows) for rows in self._TRAINING.values())
        self._priors: dict[str, float] = {}
        for label, rows in self._TRAINING.items():
            counts: Counter[str] = Counter()
            for row in rows:
                counts.update(self._features(row))
            self._label_counts[label] = counts
            self._label_totals[label] = sum(counts.values())
            vocabulary.update(counts)
            self._priors[label] = math.log(len(rows) / total_examples)
        self._vocabulary_size = max(1, len(vocabulary))
        self._latencies_ms: deque[float] = deque(maxlen=256)
        self._first_classify_ms: float | None = None

    def classify(self, text: str, context: EndpointContext) -> SemanticClassScores:
        started = time.perf_counter()
        features = self._features(text, context)
        log_scores: dict[str, float] = {}
        for label, counts in self._label_counts.items():
            denominator = self._label_totals[label] + self._vocabulary_size
            score = self._priors[label]
            for feature in features:
                score += math.log((counts[feature] + 1) / denominator)
            log_scores[label] = score
        maximum = max(log_scores.values())
        probabilities = {
            label: math.exp(score - maximum) for label, score in log_scores.items()
        }
        total = sum(probabilities.values()) or 1.0
        normalized = {label: value / total for label, value in probabilities.items()}
        label = max(normalized, key=normalized.get)
        latency_ms = (time.perf_counter() - started) * 1_000
        self._latencies_ms.append(latency_ms)
        if self._first_classify_ms is None:
            self._first_classify_ms = latency_ms
        return SemanticClassScores(
            label=label,
            confidence=round(normalized[label], 3),
            scores={key: round(value, 4) for key, value in normalized.items()},
            provider=self.name,
        )

    @property
    def model_source(self) -> str:
        return get_settings().semantic_endpointing_model_source

    @property
    def device(self) -> str:
        return get_settings().semantic_endpointing_model_device

    @property
    def cache_path(self) -> str:
        return get_settings().semantic_endpointing_model_cache_path

    @property
    def warm_start_ms(self) -> float:
        return round((time.perf_counter() - self._created_at) * 1_000, 3)

    @property
    def cold_start_ms(self) -> float | None:
        return round(self._first_classify_ms, 3) if self._first_classify_ms is not None else None

    def latency_summary(self) -> dict[str, float | None]:
        samples = sorted(self._latencies_ms)
        if not samples:
            return {"median_ms": None, "p95_ms": None}
        midpoint = len(samples) // 2
        median = (
            samples[midpoint]
            if len(samples) % 2
            else (samples[midpoint - 1] + samples[midpoint]) / 2
        )
        index = max(0, min(len(samples) - 1, math.ceil(0.95 * len(samples)) - 1))
        return {"median_ms": round(median, 3), "p95_ms": round(samples[index], 3)}

    @staticmethod
    def _features(text: str, context: EndpointContext | None = None) -> list[str]:
        folded = text.casefold()
        words = _WORD.findall(folded)
        features = [f"w:{word}" for word in words]
        features.extend(
            f"b:{left}_{right}" for left, right in zip(words, words[1:], strict=False)
        )
        compact = re.sub(r"\s+", " ", folded).strip()
        padded = f"  {compact}  "
        features.extend(
            f"c:{padded[index:index + 3]}"
            for index in range(max(0, len(padded) - 2))
        )
        semantic_vector = _semantic_vector(compact)
        features.extend(
            f"sem:{index}:{min(7, int(round(value * 8)))}"
            for index, value in enumerate(semantic_vector)
            if value > 0
        )
        features.append(f"n:{min(len(words), 16)}")
        features.append(f"chars:{min(len(compact), 120) // 8}")
        features.append(f"shape:{'_'.join(_token_shape(token) for token in words[:4]) or 'empty'}")
        features.append(f"tailshape:{_token_shape(words[-1]) if words else 'empty'}")
        features.append(f"has_ellipsis:{int(compact.endswith(('...', '…')))}")
        features.append(f"has_question:{int(compact.endswith('?'))}")
        features.append(f"has_comma:{int(',' in compact)}")
        features.append(f"has_temporal_hint:{int(bool(_DATE_OR_TIME_HINT.search(compact)))}")
        features.append(f"has_correction_tail:{int(bool(_CORRECTION_TAIL.search(compact)))}")
        features.append(f"has_list_tail:{int(bool(_LIST_TAIL.search(compact)))}")
        features.append(
            f"has_open_tail:{int(bool(re.search(r'(?:,|:|;|/|\\-|\\.\\.\\.|…)$', compact)))}"
        )
        features.append(f"leading_blank:{int(not compact)}")
        if context is not None and context.previous_transcript:
            prev_similarity = _semantic_similarity(context.previous_transcript, compact)
            features.append(f"prev_sem:{_probability_bucket(prev_similarity, scale=8)}")
            features.append(
                f"prev_change:{_probability_bucket(1.0 - prev_similarity, scale=8)}"
            )
        for index, token in enumerate(words):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            features.append(f"h:{int.from_bytes(digest[:2], 'big') % 32}")
            if len(token) <= 2:
                features.append("short_token")
            if index < 2:
                features.append(f"lead:{token}")
            if token.isdigit():
                features.append("numeric_token")
        if compact.endswith(("...", "…")):
            features.append("terminal_ellipsis")
        if compact.endswith("?"):
            features.append("terminal_question")
        if "," in compact:
            features.append(f"comma:{min(compact.count(','), 4)}")
        if context is not None:
            features.append(f"intent:{context.current_intent or 'none'}")
            features.append(f"goal:{_hash_bucket(context.current_goal or '')}")
            features.append(f"topic:{_hash_bucket(context.current_topic or '')}")
            features.append(f"locale:{_hash_bucket(context.conversation_locale or '')}")
            features.append(
                f"pref:{_hash_bucket(context.user_language_preference or '')}"
            )
            features.append(
                f"detected_lang:{_language_primary_subtag(context.detected_language)}"
            )
            features.append(
                f"lang_conf:{_probability_bucket(context.language_confidence, scale=8)}"
            )
            features.append(f"code_switch:{int(context.code_switching_detected)}")
            for slot in context.missing_slots:
                features.append(f"slot:{slot}")
            for language in context.languages:
                features.append(f"lang_hist:{_language_primary_subtag(language)}")
        return features


class MultilingualEmbeddingEndpointClassifier:
    """Low-latency multilingual embeddings with a calibrated structural head.

    The embedding model supplies the language-independent semantic representation.
    The small head intentionally uses intent descriptions rather than per-language
    phrase dictionaries; acoustic and conversation-state safeguards remain in
    ``TranscriptEndpointModel``.
    """

    name = "multilingual_semantic_local"
    fallback_active = False
    model_version = _MODEL_VERSION
    model_size = "118 MB (quantized ONNX)"
    _MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    _PROTOTYPES = {
        "complete_command": "a complete executable user command with all necessary details",
        "complete_question": "a fully formed question that can be answered now",
        "incomplete_request": "an unfinished request missing its object person date time or required detail",
        "thinking_continuation": "the speaker is hesitating remembering or explicitly continuing their thought",
        "list_continuation": "an unfinished enumeration with more list items expected",
        "completed_list": "a completed enumeration containing its final item",
        "correction": "a self correction whose replacement value has been supplied",
        "confirmation": "a short complete confirmation or acceptance",
        "rejection": "a short complete rejection or negative answer",
        "cancellation": "a short complete cancellation or stop instruction",
    }

    def __init__(self) -> None:
        settings = get_settings()
        started = time.perf_counter()
        from fastembed import TextEmbedding

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            self._embedder = TextEmbedding(
                settings.semantic_endpointing_model,
                cache_dir=settings.semantic_endpointing_model_cache_path,
            )
            vectors = list(self._embedder.embed(list(self._PROTOTYPES.values())))
        self._labels = tuple(self._PROTOTYPES)
        self._prototype_vectors = np.asarray(vectors, dtype=np.float32)
        prototype_norms = np.linalg.norm(self._prototype_vectors, axis=1, keepdims=True)
        self._prototype_vectors /= np.maximum(prototype_norms, 1e-9)
        self._latencies_ms: deque[float] = deque(maxlen=256)
        self._cold_start_ms = (time.perf_counter() - started) * 1_000
        self._warm_start_ms = 0.0
        self._lock = threading.RLock()

    @property
    def model_name(self) -> str:
        return self._MODEL

    def classify(self, text: str, context: EndpointContext) -> SemanticClassScores:
        started = time.perf_counter()
        with self._lock:
            vector = np.asarray(next(self._embedder.embed([text or " "])), dtype=np.float32)
            vector /= max(float(np.linalg.norm(vector)), 1e-9)
            similarities = self._prototype_vectors @ vector
        # Temperature-scaled cosine similarities form a compact calibrated head.
        logits = (similarities - float(np.max(similarities))) / 0.12
        probabilities = np.exp(logits)
        probabilities /= float(np.sum(probabilities)) or 1.0
        scores = {
            label: float(probabilities[index])
            for index, label in enumerate(self._labels)
        }
        words = _WORD.findall(text.casefold())
        compact = text.strip()
        if context.missing_slots:
            scores["incomplete_request"] += 0.8
        if compact.endswith(("...", "…", ",", ":")):
            scores["incomplete_request"] += 0.28
        if len(words) <= 3 and scores["confirmation"] + scores["rejection"] + scores["cancellation"] > 0.18:
            for label in ("confirmation", "rejection", "cancellation"):
                scores[label] *= 1.45
        total = sum(scores.values()) or 1.0
        scores = {label: value / total for label, value in scores.items()}
        label = max(scores, key=scores.get)
        latency_ms = (time.perf_counter() - started) * 1_000
        self._latencies_ms.append(latency_ms)
        return SemanticClassScores(
            label=label,
            confidence=round(scores[label], 3),
            scores={key: round(value, 4) for key, value in scores.items()},
            provider=self.name,
        )

    @property
    def model_source(self) -> str:
        return "Hugging Face / Qdrant FastEmbed ONNX export"

    @property
    def device(self) -> str:
        return get_settings().semantic_endpointing_model_device

    @property
    def cold_start_ms(self) -> float:
        return round(self._cold_start_ms, 3)

    @property
    def warm_start_ms(self) -> float:
        return round(self._warm_start_ms, 3)

    def latency_summary(self) -> dict[str, float | None]:
        samples = sorted(self._latencies_ms)
        if not samples:
            return {"median_ms": None, "p95_ms": None}
        return {
            "median_ms": round(float(np.median(samples)), 3),
            "p95_ms": round(float(np.percentile(samples, 95)), 3),
        }


class LinguisticEndpointFallback:
    """Explicit bounded fallback when the local semantic model cannot initialize."""

    name = "linguistic_endpoint_fallback"
    fallback_active = True

    def classify(self, text: str, context: EndpointContext) -> SemanticClassScores:
        folded = text.casefold().strip()
        words = _WORD.findall(folded)
        if not folded:
            label = "incomplete_request"
        elif folded in {"abeg", "stop am", "cancel am", "leave am"}:
            label = "confirmation" if folded == "abeg" else "complete_command"
        elif words and words[-1] in _SHORT_COMMANDS:
            label = "confirmation" if words[-1] in {"yes", "no", "confirm"} else "complete_command"
        elif any(marker in folded for marker in _CORRECTION_MARKERS):
            label = "correction"
        elif any(marker in folded for marker in _THINKING_MARKERS):
            label = "thinking_continuation"
        elif folded.endswith(("...", "…")) or (words and words[-1] in _INCOMPLETE_TAILS):
            label = "incomplete_request"
        elif text.rstrip().endswith("?"):
            label = "complete_question"
        elif _DATE_OR_TIME_HINT.search(folded) and folded.endswith(("at", "for", "on", "a", "à", "au")):
            label = "incomplete_request"
        else:
            label = "complete_command"
        return SemanticClassScores(
            label=label,
            confidence=0.58,
            scores={label: 1.0},
            provider=self.name,
            fallback_active=True,
        )


@lru_cache(maxsize=1)
def create_semantic_endpoint_classifier() -> SemanticEndpointClassifier:
    settings = get_settings()
    provider = settings.semantic_endpointing_provider.strip().lower()
    if provider in {"multilingual_semantic", "multilingual_semantic_hybrid"}:
        try:
            return MultilingualEmbeddingEndpointClassifier()
        except Exception:
            if settings.semantic_endpointing_fallback_mode == "disabled":
                raise
            log.exception("multilingual_endpoint_model_initialization_failed")
            return LinguisticEndpointFallback()
    if provider == "local_statistical":
        return LocalStatisticalEndpointClassifier()
    if provider in {"linguistic_fallback", "multilingual_fallback"}:
        return LinguisticEndpointFallback()
    raise ValueError(f"Unsupported semantic endpointing provider: {provider}")


class TranscriptEndpointModel:
    """Model-backed semantic endpointing over incremental STT hypotheses."""

    def __init__(
        self,
        *,
        classifier: SemanticEndpointClassifier | None = None,
        context: EndpointContext | None = None,
    ) -> None:
        self.classifier = classifier or create_semantic_endpoint_classifier()
        self._context = context or EndpointContext()
        self._previous_topic = self._context.current_topic or ""
        self._text = ""
        self._previous_text = ""
        self._confidence = 0.0
        self._stability = 0.0
        self._language = "unknown"
        self._language_confidence = 0.0
        self._languages: tuple[str, ...] = ()
        self._code_switching_detected = False
        self._language_changed = False
        self._semantic_similarity = 0.0
        self._recent_change_ratio = 0.0
        self._classification = SemanticClassScores(
            label="incomplete_request",
            confidence=0.0,
            scores={},
            provider=self.classifier.name,
            fallback_active=self.classifier.fallback_active,
        )
        self._classifier_latency_ms = 0.0
        self._model_version = _MODEL_VERSION
        self._last_partial_sequence = -1
        self._model_failure_reason: str | None = None

    def update(
        self,
        text: str,
        *,
        confidence: float | None,
        stability: float | None,
        language: str | None,
        language_confidence: float | None = None,
        languages: list[str] | tuple[str, ...] | None = None,
        code_switching_detected: bool | None = None,
        partial_sequence: int | None = None,
    ) -> bool:
        if partial_sequence is not None and partial_sequence <= self._last_partial_sequence:
            return False
        if partial_sequence is not None:
            self._last_partial_sequence = partial_sequence
        clean = text.strip()
        self._recent_change_ratio = (
            1.0
            if not self._text and clean
            else round(1.0 - SequenceMatcher(None, self._text, clean).ratio(), 3)
        )
        self._previous_text = self._text
        self._text = clean
        self._confidence = max(0.0, min(1.0, confidence or 0.0))
        self._stability = max(0.0, min(1.0, stability or 0.0))
        normalized_language = _normalize_language(language)
        self._language_changed = (
            self._language != "unknown"
            and normalized_language != "unknown"
            and normalized_language != self._language
        )
        self._language = normalized_language
        self._language_confidence = max(
            0.0, min(1.0, language_confidence or 0.0)
        )
        normalized_languages = tuple(
            dict.fromkeys(
                item
                for item in (_normalize_language(language) for language in (languages or ()))
                if item != "unknown"
            )
        )
        if normalized_languages:
            self._languages = normalized_languages
        elif self._language != "unknown":
            self._languages = (self._language,)
        else:
            self._languages = ("unknown",)
        if code_switching_detected is not None:
            self._code_switching_detected = code_switching_detected
        elif len(self._languages) > 1:
            self._code_switching_detected = True
        self._semantic_similarity = (
            _semantic_similarity(self._previous_text, self._text)
            if self._previous_text and self._text
            else 0.0
        )
        started = time.perf_counter()
        self._model_failure_reason = None
        try:
            self._classification = self.classifier.classify(
                self._text,
                EndpointContext(
                    current_topic=self._context.current_topic,
                    current_goal=self._context.current_goal,
                    current_intent=self._context.current_intent,
                    pending_action=self._context.pending_action,
                    missing_slots=self._context.missing_slots,
                    conversation_locale=self._context.conversation_locale,
                    user_language_preference=self._context.user_language_preference,
                    detected_language=self._language,
                    language_confidence=self._language_confidence,
                    languages=self._languages,
                    code_switching_detected=self._code_switching_detected,
                    previous_transcript=self._previous_text,
                ),
            )
        except TimeoutError:
            log.exception("semantic_endpoint_classifier_timeout")
            self._model_failure_reason = "semantic_model_timeout"
            self._classification = SemanticClassScores(
                label="incomplete_request",
                confidence=0.0,
                scores={},
                provider=self.classifier.name,
                fallback_active=True,
            )
        except Exception:
            log.exception("semantic_endpoint_classifier_failed")
            self._model_failure_reason = "semantic_model_failure"
            self._classification = SemanticClassScores(
                label="incomplete_request",
                confidence=0.0,
                scores={},
                provider=self.classifier.name,
                fallback_active=True,
            )
        self._classifier_latency_ms = (time.perf_counter() - started) * 1_000
        timeout_ms = get_settings().semantic_endpointing_inference_timeout_seconds * 1_000
        if self._classifier_latency_ms > timeout_ms:
            log.warning(
                "semantic_endpoint_latency_exceeded_slo latency_ms=%.3f slo_ms=%.3f",
                self._classifier_latency_ms,
                timeout_ms,
            )
        return True

    def reset(self) -> None:
        self._text = ""
        self._previous_text = ""
        self._confidence = 0.0
        self._stability = 0.0
        self._language = "unknown"
        self._language_confidence = 0.0
        self._languages = ()
        self._code_switching_detected = False
        self._language_changed = False
        self._semantic_similarity = 0.0
        self._recent_change_ratio = 0.0
        self._last_partial_sequence = -1
        self._model_failure_reason = None
        self._classification = SemanticClassScores(
            label="incomplete_request",
            confidence=0.0,
            scores={},
            provider=self.classifier.name,
            fallback_active=self.classifier.fallback_active,
        )

    @property
    def completion_probability(self) -> float:
        return self.evaluate(0).completion_probability

    @property
    def model_version(self) -> str:
        return self._model_version

    def evaluate(self, silence_ms: int) -> SemanticEndpointDecision:
        settings = get_settings()
        minimum = max(160, settings.semantic_endpointing_min_wait_ms)
        maximum = max(minimum + 200, settings.semantic_endpointing_max_wait_ms)
        confidence_floor = max(0.3, float(settings.semantic_endpointing_min_confidence))
        code_switch_floor = max(0.35, float(settings.semantic_endpointing_code_switch_threshold))
        folded = self._text.casefold().strip()
        words = _WORD.findall(folded)
        label = self._classification.label
        label_confidence = self._classification.confidence
        missing_slots = self._required_slots()
        low_signal = self._confidence < 0.45 or self._stability < 0.35
        short_utterance = len(words) <= 3 and bool(words)
        code_switching = self._code_switching_detected or len(self._languages) > 1
        semantically_complete = self._semantic_similarity >= 0.58
        semantically_open = self._semantic_similarity < 0.42
        correction_in_progress = self._recent_change_ratio >= 0.14 and self._stability < 0.82
        final_punctuation = folded.endswith((".", "?", "!"))
        trailing_fragment = folded.rsplit("...", 1)[-1].strip() if "..." in folded else ""
        resolved_after_suspension = (
            final_punctuation and len(_WORD.findall(trailing_fragment)) >= 2
        )
        structurally_resolved = final_punctuation and len(words) >= 4
        supported_languages = {
            item.strip().casefold()
            for item in str(
                getattr(
                    settings,
                    "semantic_endpointing_supported_languages",
                    "en,pcm,fr",
                )
            ).split(",")
            if item.strip()
        }
        language_support_mode = (
            "supported"
            if self._language in supported_languages
            else "language-agnostic fallback active"
        )

        incomplete_labels = {
            "incomplete_request",
            "thinking_continuation",
            "list_continuation",
            "date_continuation",
            "time_continuation",
            "person_continuation",
            "hesitation",
            "unstable_partial_transcript",
            "noisy_partial_transcript",
            "low_confidence_transcript",
        }
        complete_labels = {
            "complete_command",
            "complete_question",
            "completed_list",
            "confirmation",
            "rejection",
            "cancellation",
            "short_command",
            "maximum_duration_completion",
        }

        decision = EndpointDecision.UNCERTAIN
        reason = "semantic_completion_uncertain"
        wait_ms = min(maximum, 850)
        completion = 0.5

        if self._model_failure_reason:
            decision = EndpointDecision.UNCERTAIN
            reason = self._model_failure_reason
            wait_ms = min(maximum, 900)
            completion = 0.35
        elif missing_slots:
            decision = EndpointDecision.CONTINUE_LISTENING
            reason = f"required_slots_missing:{','.join(missing_slots)}"
            wait_ms = maximum
            completion = 0.12
        elif code_switching and (
            self._language_confidence < code_switch_floor or silence_ms < minimum + 200
        ):
            decision = EndpointDecision.UNCERTAIN
            reason = "code_switching_detected"
            wait_ms = min(maximum, 950)
            completion = 0.35
        elif correction_in_progress:
            decision = EndpointDecision.UNCERTAIN
            reason = "recent_partial_correction_unstable"
            wait_ms = min(maximum, 1_000)
            completion = 0.42
        elif (
            code_switching
            and silence_ms >= 700
            and self._stability >= 0.75
            and self._confidence >= 0.7
            and len(words) >= 4
            and not folded.endswith(("...", "…", ",", ":"))
        ):
            decision = EndpointDecision.LIKELY_COMPLETE
            reason = "stable_code_switched_completion"
            wait_ms = 700
            completion = 0.82
        elif short_utterance and label in {
            "short_command",
            "confirmation",
            "rejection",
            "cancellation",
        } and not folded.endswith(("...", "…", ",", ":")):
            decision = EndpointDecision.FORCE_COMPLETE
            reason = f"semantic_{label}"
            wait_ms = minimum
            completion = 0.98
        elif (
            short_utterance
            and self._confidence >= confidence_floor
            and self._stability >= 0.6
            and not folded.endswith(("...", "…", ",", ":"))
        ):
            decision = EndpointDecision.FORCE_COMPLETE
            reason = "complete_short_command"
            wait_ms = minimum
            completion = 0.98
        elif folded.endswith(("...", "…", ",", ":")):
            decision = EndpointDecision.CONTINUE_LISTENING
            reason = "semantically_open_utterance"
            wait_ms = maximum
            completion = 0.16
        elif structurally_resolved and (
            label not in {"thinking_continuation"}
            or resolved_after_suspension
            or "..." not in folded
        ):
            decision = EndpointDecision.LIKELY_COMPLETE
            reason = "stable_semantic_completion"
            wait_ms = max(minimum, 440)
            completion = 0.86
        elif label in {"complete_command", "complete_question"}:
            decision = EndpointDecision.LIKELY_COMPLETE
            reason = f"semantic_{label}"
            wait_ms = max(minimum, 440)
            completion = 0.9 if label == "complete_question" else 0.88
        elif label == "completed_list":
            decision = EndpointDecision.LIKELY_COMPLETE
            reason = "list_items_resolved"
            wait_ms = max(minimum, 560)
            completion = 0.84
        elif label == "maximum_duration_completion":
            decision = EndpointDecision.FORCE_COMPLETE
            reason = "max_utterance"
            wait_ms = minimum
            completion = 0.96
        elif label == "correction":
            if correction_in_progress or semantically_open:
                decision = EndpointDecision.CONTINUE_LISTENING
                reason = "correction_in_progress"
                wait_ms = maximum
                completion = 0.24
            else:
                decision = EndpointDecision.LIKELY_COMPLETE
                reason = "correction_resolved"
                wait_ms = max(minimum, 560)
                completion = 0.84
        elif label in incomplete_labels:
            decision = EndpointDecision.CONTINUE_LISTENING
            reason = "semantically_incomplete_utterance"
            wait_ms = maximum
            completion = 0.16
        elif label in complete_labels or (semantically_complete and self._confidence >= 0.7):
            decision = EndpointDecision.LIKELY_COMPLETE
            reason = (
                f"semantic_{label}" if label in complete_labels else "stable_semantic_completion"
            )
            wait_ms = max(minimum, 440)
            completion = 0.86
        elif silence_ms >= 900 and self._stability >= 0.7 and semantically_complete:
            decision = EndpointDecision.LIKELY_COMPLETE
            reason = "stable_semantic_completion_after_pause"
            wait_ms = min(maximum, 900)
            completion = 0.76
        elif low_signal:
            decision = EndpointDecision.UNCERTAIN
            reason = "unstable_or_low_confidence_transcript"
            wait_ms = min(maximum, 1000)
            completion = 0.4
        elif semantically_open:
            decision = EndpointDecision.CONTINUE_LISTENING
            reason = "semantically_incomplete_utterance"
            wait_ms = maximum
            completion = 0.18
        elif label in {"hesitation", "thinking_continuation"}:
            decision = EndpointDecision.CONTINUE_LISTENING
            reason = "user_is_thinking"
            wait_ms = maximum
            completion = 0.18
        else:
            decision = EndpointDecision.UNCERTAIN
            reason = "semantic_completion_uncertain"
            wait_ms = min(maximum, 850)
            completion = 0.5

        confidence = min(
            0.99,
            max(
                0.05,
                0.34 * label_confidence
                + 0.24 * self._confidence
                + 0.18 * self._stability
                + 0.12 * self._semantic_similarity
                + 0.08 * self._language_confidence
                + 0.04 * (1.0 - min(1.0, self._recent_change_ratio)),
            ),
        )
        if code_switching:
            confidence *= 0.92
            if decision == EndpointDecision.LIKELY_COMPLETE and silence_ms < 700:
                decision = EndpointDecision.UNCERTAIN
                reason = "code_switching_detected"
                wait_ms = min(maximum, max(wait_ms, 850))
                completion = min(completion, 0.58)
        if self._recent_change_ratio > 0.08 and self._stability < 0.8:
            wait_ms = min(maximum, wait_ms + 180)
            confidence *= 0.9
            if decision == EndpointDecision.LIKELY_COMPLETE:
                decision = EndpointDecision.UNCERTAIN
                reason = "recent_partial_correction_unstable"
                completion = min(completion, 0.58)

        return SemanticEndpointDecision(
            decision=decision,
            confidence=round(confidence, 3),
            reason=reason,
            recommended_wait_ms=wait_ms,
            completion_probability=round(completion, 3),
            classifier_label=label,
            classifier_provider=self._classification.provider,
            model_version=self._model_version,
            classifier_latency_ms=self._classifier_latency_ms,
            required_slots_remaining=missing_slots,
            transcript_stability=round(self._stability, 3),
            recent_change_ratio=self._recent_change_ratio,
            detected_language=self._language,
            language_confidence=round(self._language_confidence, 3),
            code_switching_detected=code_switching,
            languages=self._languages,
            language_support_mode=language_support_mode,
            fallback_reason=(
                self._model_failure_reason
                or ("semantic_model_unavailable" if self.classifier.fallback_active else None)
            ),
        )

    def _required_slots(self) -> tuple[str, ...]:
        if self._context.missing_slots:
            return self._context.missing_slots
        pending_action = self._context.pending_action or {}
        if isinstance(pending_action, dict):
            missing = pending_action.get("missing_slots") or pending_action.get("missing")
            if isinstance(missing, (list, tuple)):
                return tuple(
                    dict.fromkeys(
                        str(slot).strip()
                        for slot in missing
                        if str(slot).strip()
                    )
                )
        return ()

    @staticmethod
    def _has_time_reference(text: str) -> bool:
        return bool(
            re.search(
                r"\b(\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)?|today|tomorrow|yesterday|mon(day)?|tue(sday)?|wed(nesday)?|thu(rsday)?|fri(day)?|sat(urday)?|sun(day)?)\b",
                text.casefold(),
            )
        )

    @staticmethod
    def _has_person_reference(text: str) -> bool:
        return bool(re.search(r"\bwith\s+[\w'-]+", text.casefold()))

    @property
    def topic_changed(self) -> bool:
        current = set(_WORD.findall(self._text.casefold()))
        previous = set(_WORD.findall(self._previous_topic.casefold()))
        if len(current) < 4 or len(previous) < 3:
            return False
        overlap = len(current & previous) / max(1, len(current | previous))
        return overlap < 0.08


class HybridTurnDetector:
    """Fuses neural speech probability, silence, transcript completion, and context."""

    def __init__(
        self,
        *,
        speech_provider: SpeechProbabilityProvider | None = None,
        previous_topic: str | None = None,
        endpoint_context: EndpointContext | None = None,
        semantic_classifier: SemanticEndpointClassifier | None = None,
        start_threshold: float = 0.55,
        end_threshold: float = 0.35,
        preroll_ms: int = 320,
        thinking_pause_ms: int = 320,
        max_utterance_ms: int = 20_000,
    ) -> None:
        self.speech_provider = speech_provider or create_speech_probability_provider()
        context = endpoint_context or EndpointContext(current_topic=previous_topic)
        self.semantic = TranscriptEndpointModel(
            classifier=semantic_classifier,
            context=context,
        )
        self._start_threshold = start_threshold
        self._end_threshold = end_threshold
        self._start_min_ms = get_settings().neural_vad_start_min_ms
        self._noise_probability = 0.05
        self._thinking_pause_ms = thinking_pause_ms
        self._max_utterance_ms = max_utterance_ms
        self._preroll_frames: deque[bytes] = deque()
        self._preroll_bytes = SAMPLE_RATE * SAMPLE_WIDTH_BYTES * preroll_ms // 1_000
        self._preroll_size = 0
        self._clock_ms = 0
        self._speech_started_ms: int | None = None
        self._last_speech_ms = 0
        self._speech_run_ms = 0
        self._pause_emitted = False
        self._active = False
        self._ai_was_speaking = False
        self._last_acoustic_state = AcousticState.SILENCE

    @property
    def active(self) -> bool:
        return self._active

    @property
    def adaptive_start_threshold(self) -> float:
        return max(self._start_threshold, min(0.78, self._noise_probability + 0.2))

    @property
    def adaptive_end_threshold(self) -> float:
        return max(self._end_threshold, min(0.6, self._noise_probability + 0.1))

    def update_transcript(
        self,
        text: str,
        *,
        confidence: float | None = None,
        stability: float | None = None,
        language: str | None = None,
        language_confidence: float | None = None,
        languages: list[str] | tuple[str, ...] | None = None,
        code_switching_detected: bool | None = None,
        partial_sequence: int | None = None,
    ) -> bool:
        return self.semantic.update(
            text,
            confidence=confidence,
            stability=stability,
            language=language,
            language_confidence=language_confidence,
            languages=languages,
            code_switching_detected=code_switching_detected,
            partial_sequence=partial_sequence,
        )

    def process(
        self, pcm: bytes, *, ai_speaking: bool = False
    ) -> list[TurnDetectionEvent]:
        frame_ms = len(pcm) * 1_000 // (SAMPLE_RATE * SAMPLE_WIDTH_BYTES)
        self._clock_ms += frame_ms
        probability = self.speech_provider.score(pcm)
        self._append_preroll(pcm)
        events: list[TurnDetectionEvent] = []

        if not self._active:
            if probability < self.adaptive_start_threshold:
                self._noise_probability = (
                    0.95 * self._noise_probability + 0.05 * probability
                )
            effective_start_threshold = self.adaptive_start_threshold
            if ai_speaking and get_settings().neural_vad_echo_suppression_enabled:
                effective_start_threshold = max(
                    effective_start_threshold,
                    get_settings().neural_vad_echo_start_threshold,
                )
            self._speech_run_ms = (
                self._speech_run_ms + frame_ms
                if probability >= effective_start_threshold
                else 0
            )
            if self._speech_run_ms >= self._start_min_ms:
                self._active = True
                self._speech_started_ms = self._clock_ms - self._speech_run_ms
                self._last_speech_ms = self._clock_ms
                self._pause_emitted = False
                self._ai_was_speaking = ai_speaking
                acoustic_state = (
                    AcousticState.BARGE_IN
                    if ai_speaking
                    else AcousticState.SPEECH_STARTED
                )
                events.append(
                    TurnDetectionEvent(
                        signal=TurnSignal.SPEECH_STARTED,
                        speech_probability=probability,
                        audio_ms=self._clock_ms,
                        pause_kind=(
                            PauseKind.INTERRUPTED
                            if ai_speaking
                            else PauseKind.TOPIC_CHANGE
                            if self.semantic.topic_changed
                            else None
                        ),
                        preroll_pcm=b"".join(self._preroll_frames),
                        acoustic_decision=self._acoustic_decision(
                            acoustic_state,
                            probability,
                            reason=(
                                "neural_speech_during_playback"
                                if ai_speaking
                                else "consecutive_neural_speech"
                            ),
                            ai_speaking=ai_speaking,
                        ),
                    )
                )
            return events

        speech_started_ms = (
            self._speech_started_ms
            if self._speech_started_ms is not None
            else self._clock_ms
        )
        utterance_ms = self._clock_ms - speech_started_ms
        if utterance_ms >= self._max_utterance_ms:
            silence_ms = max(0, self._clock_ms - self._last_speech_ms)
            endpoint_decision = self.semantic.evaluate(silence_ms)
            events.append(
                TurnDetectionEvent(
                    signal=TurnSignal.ENDPOINT,
                    speech_probability=probability,
                    audio_ms=self._clock_ms,
                    silence_ms=silence_ms,
                    completion_probability=(
                        endpoint_decision.completion_probability
                    ),
                    pause_kind=(
                        PauseKind.INTERRUPTED
                        if self._ai_was_speaking
                        else PauseKind.TOPIC_CHANGE
                        if self.semantic.topic_changed
                        else PauseKind.FINISHED
                    ),
                    reason="max_utterance",
                    endpoint_decision=endpoint_decision,
                    acoustic_decision=self._acoustic_decision(
                        AcousticState.FORCED_ENDPOINT,
                        probability,
                        reason="maximum_utterance_duration",
                        silence_ms=silence_ms,
                        utterance_ms=utterance_ms,
                        ai_speaking=self._ai_was_speaking,
                    ),
                )
            )
            self._reset_turn()
            return events

        if probability >= self.adaptive_end_threshold:
            if self._pause_emitted:
                events.append(
                    TurnDetectionEvent(
                        signal=TurnSignal.SPEECH_RESUMED,
                        speech_probability=probability,
                        audio_ms=self._clock_ms,
                        pause_kind=PauseKind.THINKING,
                        acoustic_decision=self._acoustic_decision(
                            AcousticState.SPEECH_ACTIVE,
                            probability,
                            reason="speech_resumed_after_contextual_pause",
                            utterance_ms=utterance_ms,
                            ai_speaking=self._ai_was_speaking,
                        ),
                    )
                )
            self._last_speech_ms = self._clock_ms
            self._pause_emitted = False
            return events

        silence_ms = self._clock_ms - self._last_speech_ms
        endpoint_decision = self.semantic.evaluate(silence_ms)
        completion = endpoint_decision.completion_probability
        if silence_ms >= self._thinking_pause_ms and not self._pause_emitted:
            self._pause_emitted = True
            events.append(
                TurnDetectionEvent(
                    signal=TurnSignal.THINKING_PAUSE,
                    speech_probability=probability,
                    audio_ms=self._clock_ms,
                    silence_ms=silence_ms,
                    completion_probability=completion,
                    pause_kind=PauseKind.THINKING,
                    reason=endpoint_decision.reason,
                    endpoint_decision=endpoint_decision,
                    acoustic_decision=self._acoustic_decision(
                        AcousticState.THINKING_PAUSE,
                        probability,
                        reason=endpoint_decision.reason,
                        silence_ms=silence_ms,
                        utterance_ms=utterance_ms,
                        ai_speaking=self._ai_was_speaking,
                    ),
                )
            )

        endpoint_ms = endpoint_decision.recommended_wait_ms
        if silence_ms >= endpoint_ms:
            pause_kind = (
                PauseKind.INTERRUPTED
                if self._ai_was_speaking
                else PauseKind.TOPIC_CHANGE
                if self.semantic.topic_changed
                else PauseKind.FINISHED
            )
            events.append(
                TurnDetectionEvent(
                    signal=TurnSignal.ENDPOINT,
                    speech_probability=probability,
                    audio_ms=self._clock_ms,
                    silence_ms=silence_ms,
                    completion_probability=completion,
                    pause_kind=pause_kind,
                    reason="semantic_silence",
                    endpoint_decision=endpoint_decision,
                    acoustic_decision=self._acoustic_decision(
                        AcousticState.SPEECH_ENDED,
                        probability,
                        reason="contextual_pause_elapsed",
                        silence_ms=silence_ms,
                        utterance_ms=utterance_ms,
                        ai_speaking=self._ai_was_speaking,
                    ),
                )
            )
            self._reset_turn()
        return events

    def cancel(self) -> None:
        self._reset_turn()

    def diagnostics(self) -> dict[str, Any]:
        settings = get_settings()
        provider_diagnostics = getattr(
            self.speech_provider, "diagnostics", lambda: {
                "provider": self.speech_provider.name,
                "fallback_active": getattr(self.speech_provider, "fallback_active", False),
            }
        )()
        return {
            **provider_diagnostics,
            "frame_ms": settings.neural_vad_frame_ms,
            "start_threshold": self._start_threshold,
            "adaptive_start_threshold": self.adaptive_start_threshold,
            "end_threshold": self._end_threshold,
            "adaptive_end_threshold": self.adaptive_end_threshold,
            "start_min_ms": settings.neural_vad_start_min_ms,
            "thinking_pause_ms": self._thinking_pause_ms,
            "preroll_ms": self._preroll_bytes * 1_000 // (SAMPLE_RATE * SAMPLE_WIDTH_BYTES),
            "max_utterance_ms": self._max_utterance_ms,
            "fallback_mode": settings.neural_vad_fallback_mode,
            "production_fallback_policy": settings.neural_vad_production_fallback_policy,
            "echo_suppression_enabled": settings.neural_vad_echo_suppression_enabled,
            "active_state": self._last_acoustic_state.value,
        }

    def _acoustic_decision(
        self,
        state: AcousticState,
        probability: float,
        *,
        reason: str,
        silence_ms: int = 0,
        utterance_ms: int = 0,
        ai_speaking: bool = False,
    ) -> AcousticTurnDecision:
        self._last_acoustic_state = state
        confidence = probability if state in {
            AcousticState.SPEECH_STARTED,
            AcousticState.SPEECH_ACTIVE,
            AcousticState.BARGE_IN,
        } else 1.0 - probability
        return AcousticTurnDecision(
            state=state,
            confidence=max(0.0, min(1.0, confidence)),
            reason=reason,
            speech_probability=probability,
            silence_ms=silence_ms,
            utterance_ms=utterance_ms,
            ai_speaking=ai_speaking,
            provider=self.speech_provider.name,
        )

    def _append_preroll(self, pcm: bytes) -> None:
        if not pcm:
            return
        self._preroll_frames.append(pcm)
        self._preroll_size += len(pcm)
        while self._preroll_size > self._preroll_bytes and self._preroll_frames:
            self._preroll_size -= len(self._preroll_frames.popleft())

    def _reset_turn(self) -> None:
        self._active = False
        self._speech_started_ms = None
        self._speech_run_ms = 0
        self._pause_emitted = False
        self._ai_was_speaking = False
        self.semantic.reset()
        reset = getattr(self.speech_provider, "reset", None)
        if reset is not None:
            reset()
        self._last_acoustic_state = AcousticState.SILENCE
