from __future__ import annotations

import statistics
import time

import pytest

from app.services.stt_provider import STTPartial
from app.services.turn_detection import (
    EndpointContext,
    EndpointDecision,
    HybridTurnDetector,
    SemanticClassScores,
    TranscriptEndpointModel,
    TurnSignal,
)
from fixtures.endpoint_regression_corpus import build_endpoint_regression_corpus


def _context_for(category: str) -> EndpointContext:
    if category in {"date_continuation", "time_continuation", "person_continuation"}:
        return EndpointContext(current_intent="schedule_meeting", missing_slots=("person", "date_or_time"))
    if category in {"incomplete_statement"}:
        return EndpointContext(current_intent="schedule_meeting", missing_slots=("person",))
    if category == "incomplete_question":
        return EndpointContext(current_intent="calendar_query", missing_slots=("question_detail",))
    if category == "list_continuation":
        return EndpointContext(current_intent="list_update", missing_slots=("next_list_item",))
    return EndpointContext()


def _run_case(model: TranscriptEndpointModel, scenario) -> tuple[str, float, bool]:
    model.reset()
    text = scenario.partial_sequence[-1]
    context = _context_for(scenario.category)
    model._context = context  # type: ignore[attr-defined]
    model.update(
        text,
        confidence=scenario.stt_confidence,
        stability=0.92 if "unstable" not in scenario.category and "noisy" not in scenario.category and "low_confidence" not in scenario.category else 0.58,
        language=scenario.language,
        language_confidence=scenario.language_confidence,
        languages=(scenario.language, "pcm") if scenario.code_switching_detected else (scenario.language,),
        code_switching_detected=scenario.code_switching_detected,
    )
    decision = model.evaluate(scenario.silence_ms)
    return decision.decision.value, decision.recommended_wait_ms, decision.code_switching_detected


def test_multilingual_regression_corpus_has_three_hundred_scenarios():
    corpus = build_endpoint_regression_corpus()
    assert len(corpus) == 300
    assert {case.language for case in corpus} == {"en", "pcm", "fr"}
    assert {case.category for case in corpus} == {
        "complete_statement",
        "incomplete_statement",
        "complete_question",
        "incomplete_question",
        "list_continuation",
        "completed_list",
        "correction",
        "hesitation",
        "confirmation",
        "rejection",
        "cancellation",
        "short_command",
        "date_continuation",
        "time_continuation",
        "person_continuation",
        "code_switching",
        "low_confidence_transcript",
        "unstable_partial_transcript",
        "noisy_partial_transcript",
        "maximum_duration_completion",
    }


def test_multilingual_endpoint_model_meets_language_specific_thresholds():
    corpus = build_endpoint_regression_corpus()
    model = TranscriptEndpointModel()
    by_language: dict[str, dict[str, int | list[int]]] = {}
    code_switch_hits = 0
    code_switch_total = 0

    for scenario in corpus:
        decision, wait_ms, code_switching_detected = _run_case(model, scenario)
        stats = by_language.setdefault(
            scenario.language,
            {"cases": 0, "false_cutoff": 0, "over_wait": 0, "waits": []},
        )
        stats["cases"] = int(stats["cases"]) + 1
        expected = scenario.expected_decision
        if expected in {"likely_complete", "force_complete"}:
            stats["waits"].append(wait_ms)  # type: ignore[union-attr]
        if expected in {"continue_listening", "uncertain"} and decision in {"likely_complete", "force_complete"}:
            stats["false_cutoff"] = int(stats["false_cutoff"]) + 1
        if expected in {"likely_complete", "force_complete"} and decision in {"continue_listening", "uncertain"}:
            stats["over_wait"] = int(stats["over_wait"]) + 1
        if scenario.category == "code_switching":
            code_switch_total += 1
            code_switch_hits += int(code_switching_detected)

    per_language_summary = {}
    for language, stats in by_language.items():
        waits = list(stats["waits"])  # type: ignore[arg-type]
        false_cutoff_rate = int(stats["false_cutoff"]) / int(stats["cases"])
        over_wait_rate = int(stats["over_wait"]) / int(stats["cases"])
        median_delay = statistics.median(waits)
        p95_delay = statistics.quantiles(waits, n=20)[18]
        per_language_summary[language] = {
            "false_cutoff_rate": false_cutoff_rate,
            "over_wait_rate": over_wait_rate,
            "median_delay": median_delay,
            "p95_delay": p95_delay,
        }
        assert false_cutoff_rate <= 0.03, per_language_summary
        assert over_wait_rate <= 0.05, per_language_summary
        assert median_delay < 750, per_language_summary
        assert p95_delay < 1500, per_language_summary

    assert code_switch_hits == code_switch_total
    assert model.classifier.name == "multilingual_semantic_local"
    assert model.evaluate(500).classifier_provider == "multilingual_semantic_local"
    assert model.evaluate(500).model_version == "endpoint-v2"


def test_missing_language_is_unknown_and_stale_language_update_is_rejected():
    partial = STTPartial(text="bonjour")
    assert partial.language == "unknown"
    model = TranscriptEndpointModel()
    assert model.update(
        "bonjour",
        confidence=0.9,
        stability=0.8,
        language="fr",
        language_confidence=0.95,
        partial_sequence=2,
    )
    assert not model.update(
        "hello",
        confidence=0.9,
        stability=0.9,
        language="en",
        language_confidence=0.99,
        partial_sequence=1,
    )
    decision = model.evaluate(500)
    assert decision.detected_language == "fr"
    assert decision.languages == ("fr",)


def test_language_change_alone_does_not_finalize_code_switched_partial():
    model = TranscriptEndpointModel()
    model.update(
        "I will call him demain",
        confidence=0.91,
        stability=0.88,
        language="fr",
        language_confidence=0.72,
        languages=("en", "fr"),
        code_switching_detected=True,
        partial_sequence=3,
    )
    decision = model.evaluate(300)
    assert decision.decision == EndpointDecision.UNCERTAIN
    assert decision.code_switching_detected is True
    assert decision.languages == ("en", "fr")


class _SlowClassifier:
    name = "slow-test-model"
    fallback_active = False

    def classify(self, text: str, context: EndpointContext) -> SemanticClassScores:
        time.sleep(0.025)
        return SemanticClassScores(
            label="complete_command",
            confidence=0.99,
            scores={"complete_command": 1.0},
            provider=self.name,
        )


class _TimeoutClassifier:
    name = "timeout-test-model"
    fallback_active = False

    def classify(self, text: str, context: EndpointContext) -> SemanticClassScores:
        raise TimeoutError("configured semantic timeout expired")


def test_slow_completed_semantic_model_keeps_correctness_decision():
    model = TranscriptEndpointModel(classifier=_SlowClassifier())
    model.update("stop", confidence=0.99, stability=0.99, language="en")
    decision = model.evaluate(500)
    assert decision.decision == EndpointDecision.FORCE_COMPLETE
    assert decision.fallback_reason is None


def test_semantic_model_timeout_is_deterministic_uncertain_fallback():
    model = TranscriptEndpointModel(classifier=_TimeoutClassifier())
    model.update("stop", confidence=0.99, stability=0.99, language="en")
    decision = model.evaluate(500)
    assert decision.decision == EndpointDecision.UNCERTAIN
    assert decision.fallback_reason == "semantic_model_timeout"
    assert decision.recommended_wait_ms == 900


class _SyntheticAudioProbability:
    name = "synthetic_prerecorded_fixture"

    def __init__(self) -> None:
        self._scores = [0.92, 0.91] + [0.04] * 40

    def score(self, pcm: bytes) -> float:
        assert len(pcm) == 1_280
        return self._scores.pop(0) if self._scores else 0.04


@pytest.mark.parametrize(
    ("language", "text", "expected"),
    [
        ("en", "Schedule a meeting with Amina tomorrow at ten.", "likely_complete"),
        ("pcm", "Stop am", "force_complete"),
        ("fr", "Qu'est-ce que j'ai aujourd'hui ?", "likely_complete"),
        ("pcm", "Remind me say...", "continue_listening"),
        ("fr", "Laisse-moi reflechir...", "continue_listening"),
        ("en", "Make it ten... actually, eleven.", "likely_complete"),
        ("pcm", "Put rice, beans, and water.", "likely_complete"),
        ("fr", "Planifie la reunion avec Awa demain a 10h.", "likely_complete"),
        ("en", "I will call him demain matin.", "likely_complete"),
    ],
)
def test_synthetic_prerecorded_multilingual_audio_fixtures(
    language: str, text: str, expected: str
):
    detector = HybridTurnDetector(speech_provider=_SyntheticAudioProbability())
    frame = b"\x00" * 1_280
    detector.process(frame)
    detector.process(frame)
    detector.update_transcript(
        text,
        confidence=0.92,
        stability=0.94,
        language=language,
        language_confidence=0.95,
    )
    endpoint = None
    for _ in range(40):
        endpoint = next(
            (
                event
                for event in detector.process(frame)
                if event.signal == TurnSignal.ENDPOINT
            ),
            None,
        )
        if endpoint is not None:
            break
    assert endpoint is not None
    assert endpoint.endpoint_decision is not None
    assert endpoint.endpoint_decision.decision.value == expected
