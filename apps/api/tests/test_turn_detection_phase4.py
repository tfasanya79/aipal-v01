from __future__ import annotations

import statistics
import time

from app.services.turn_detection import (
    AdaptiveEnergyProbability,
    EndpointContext,
    EndpointDecision,
    HybridTurnDetector,
    LinguisticEndpointFallback,
    MultilingualEmbeddingEndpointClassifier,
    PauseKind,
    SileroSpeechProbability,
    TranscriptEndpointModel,
    TurnSignal,
    create_speech_probability_provider,
)


FRAME = b"\x00" * 1_280  # 40 ms of 16 kHz mono PCM16.


class SequenceProbability:
    name = "test_neural_vad"

    def __init__(self, values: list[float], *, default: float = 0.05) -> None:
        self.values = list(values)
        self.default = default

    def score(self, _pcm: bytes) -> float:
        return self.values.pop(0) if self.values else self.default


def _start(detector: HybridTurnDetector, *, ai_speaking: bool = False):
    assert not detector.process(FRAME, ai_speaking=ai_speaking)
    events = detector.process(FRAME, ai_speaking=ai_speaking)
    assert events and events[0].signal == TurnSignal.SPEECH_STARTED
    return events[0]


def test_silero_v6_is_the_primary_neural_vad():
    provider = create_speech_probability_provider()
    assert provider.name == "silero_v6"
    probability = provider.score(FRAME)
    assert 0 <= probability <= 1


def test_thinking_pause_resumes_without_ending_the_turn():
    provider = SequenceProbability([0.9, 0.9] + [0.05] * 8 + [0.9])
    detector = HybridTurnDetector(speech_provider=provider)
    _start(detector)

    pause_events = []
    for _ in range(8):
        pause_events.extend(detector.process(FRAME))
    assert any(event.signal == TurnSignal.THINKING_PAUSE for event in pause_events)
    assert detector.active is True

    resumed = detector.process(FRAME)
    assert resumed and resumed[0].signal == TurnSignal.SPEECH_RESUMED
    assert detector.active is True


def test_complete_transcript_ends_after_short_semantic_silence():
    provider = SequenceProbability([0.9, 0.9] + [0.05] * 12)
    detector = HybridTurnDetector(speech_provider=provider)
    _start(detector)
    detector.update_transcript(
        "I have finished explaining the whole request now.",
        confidence=0.92,
        stability=0.95,
        language="en",
    )

    events = []
    for _ in range(12):
        events.extend(detector.process(FRAME))
    endpoint = next(event for event in events if event.signal == TurnSignal.ENDPOINT)
    assert endpoint.silence_ms == 440
    assert endpoint.completion_probability >= 0.72
    assert endpoint.pause_kind == PauseKind.FINISHED
    assert endpoint.endpoint_decision is not None
    assert endpoint.endpoint_decision.decision == EndpointDecision.LIKELY_COMPLETE


def test_incomplete_transcript_gets_longer_thinking_window():
    provider = SequenceProbability([0.9, 0.9] + [0.05] * 30)
    detector = HybridTurnDetector(speech_provider=provider)
    _start(detector)
    detector.update_transcript(
        "I wanted to talk to",
        confidence=0.9,
        stability=0.9,
        language="en",
    )

    early_events = []
    for _ in range(12):
        early_events.extend(detector.process(FRAME))
    assert not any(event.signal == TurnSignal.ENDPOINT for event in early_events)
    assert detector.active is True

    later_events = []
    for _ in range(24):
        later_events.extend(detector.process(FRAME))
    endpoint = next(
        event for event in later_events if event.signal == TurnSignal.ENDPOINT
    )
    assert endpoint.silence_ms == 1_400
    assert endpoint.completion_probability <= 0.35


def test_barge_in_and_topic_change_are_classified_from_context():
    interrupted = HybridTurnDetector(
        speech_provider=SequenceProbability([0.9, 0.9] + [0.05] * 30)
    )
    started = _start(interrupted, ai_speaking=True)
    assert started.pause_kind == PauseKind.INTERRUPTED

    changed = HybridTurnDetector(
        speech_provider=SequenceProbability([0.9, 0.9] + [0.05] * 12),
        previous_topic="quarterly product launch milestones",
    )
    _start(changed)
    changed.update_transcript(
        "My family holiday flight booking is complete.",
        confidence=0.95,
        stability=0.95,
        language="en",
    )
    events = []
    for _ in range(12):
        events.extend(changed.process(FRAME))
    endpoint = next(event for event in events if event.signal == TurnSignal.ENDPOINT)
    assert endpoint.pause_kind == PauseKind.TOPIC_CHANGE


def test_adaptive_energy_fallback_calibrates_and_bounds_probability():
    provider = AdaptiveEnergyProbability()
    silence = provider.score(FRAME)
    loud = provider.score((10_000).to_bytes(2, "little", signed=True) * 640)
    assert 0 <= silence < loud <= 1


def test_neural_threshold_adapts_above_persistent_background_probability():
    provider = SequenceProbability([0.5] * 100 + [0.6, 0.6, 0.9, 0.9])
    detector = HybridTurnDetector(speech_provider=provider)
    for _ in range(100):
        assert not detector.process(FRAME)
    assert detector.adaptive_start_threshold > 0.65
    assert not detector.process(FRAME)
    assert not detector.process(FRAME)
    assert not detector.process(FRAME)
    events = detector.process(FRAME)
    assert events and events[0].signal == TurnSignal.SPEECH_STARTED


def test_turn_detector_p95_is_below_phase4_budget_with_stubbed_neural_model():
    provider = SequenceProbability([], default=0.05)
    detector = HybridTurnDetector(speech_provider=provider)
    samples = []
    for _ in range(500):
        started = time.perf_counter()
        detector.process(FRAME)
        samples.append((time.perf_counter() - started) * 1_000)
    p95 = statistics.quantiles(samples, n=20)[18]
    assert p95 < 0.5, f"turn detection p95 {p95:.3f}ms exceeds 0.5ms"


def test_primary_endpoint_classifier_is_multilingual_model_not_linguistic_fallback():
    model = TranscriptEndpointModel()
    assert isinstance(model.classifier, MultilingualEmbeddingEndpointClassifier)
    assert model.classifier.fallback_active is False


def test_endpoint_context_missing_slots_overrides_superficially_complete_text():
    model = TranscriptEndpointModel(
        context=EndpointContext(
            current_intent="schedule_meeting",
            missing_slots=("participant",),
        )
    )
    model.update(
        "Tomorrow at ten.",
        confidence=0.95,
        stability=0.95,
        language="en",
    )
    decision = model.evaluate(600)
    assert decision.decision == EndpointDecision.CONTINUE_LISTENING
    assert decision.required_slots_remaining == ("participant",)
    assert decision.recommended_wait_ms == 1_400


def test_linguistic_fallback_is_explicit_and_structured():
    model = TranscriptEndpointModel(classifier=LinguisticEndpointFallback())
    model.update("Stop", confidence=0.9, stability=0.9, language="en")
    decision = model.evaluate(240)
    assert model.classifier.fallback_active is True
    assert decision.classifier_provider == "linguistic_endpoint_fallback"
    assert decision.to_transport()["decision"] == "force_complete"


def test_maximum_utterance_forces_endpoint_when_turn_started_at_zero():
    detector = HybridTurnDetector(
        speech_provider=SequenceProbability([], default=0.9),
        max_utterance_ms=240,
    )
    _start(detector)
    detector.update_transcript(
        "I am continuing a very long turn",
        confidence=0.9,
        stability=0.9,
        language="en",
    )

    endpoint = None
    for _ in range(6):
        events = detector.process(FRAME)
        endpoint = next(
            (event for event in events if event.signal == TurnSignal.ENDPOINT),
            None,
        )
        if endpoint is not None:
            break

    assert endpoint is not None
    assert endpoint.reason == "max_utterance"
    assert endpoint.endpoint_decision is not None


def test_semantic_endpointing_acceptance_fixtures_and_delay_metrics():
    fixtures = [
        ("Schedule a meeting with Stephen…", 1_200, 1_400, "continue_listening"),
        (
            "Schedule a meeting with Stephen tomorrow at 10.",
            400,
            700,
            "likely_complete",
        ),
        (
            "I want to… actually, make that Friday.",
            400,
            800,
            "likely_complete",
        ),
        ("Add milk, bread, eggs… and soap.", 400, 900, "likely_complete"),
        (
            "My meeting is at… give me a second… 3 p.m.",
            400,
            900,
            "likely_complete",
        ),
        ("What do I have today?", 400, 700, "likely_complete"),
        ("Remind me to call…", 1_200, 1_400, "continue_listening"),
        ("Stop", 200, 400, "force_complete"),
        ("Yes", 200, 400, "force_complete"),
        (
            "Schedule uh meeting Stephen tom",
            900,
            1_400,
            "uncertain",
        ),
    ]
    endpoint_delays: list[int] = []
    false_cutoffs = 0
    over_waits = 0
    classifier_latencies: list[float] = []

    for text, minimum_delay, maximum_delay, expected_decision in fixtures:
        detector = HybridTurnDetector(
            speech_provider=SequenceProbability([0.9, 0.9] + [0.05] * 40)
        )
        _start(detector)
        detector.update_transcript(
            text,
            confidence=0.35 if "uh meeting" in text else 0.92,
            stability=0.2 if "uh meeting" in text else 0.95,
            language="en",
        )
        endpoint = None
        for _ in range(40):
            events = detector.process(FRAME)
            endpoint = next(
                (event for event in events if event.signal == TurnSignal.ENDPOINT),
                None,
            )
            if endpoint is not None:
                break
        assert endpoint is not None, text
        assert endpoint.endpoint_decision is not None
        assert endpoint.endpoint_decision.decision.value == expected_decision
        endpoint_delays.append(endpoint.silence_ms)
        classifier_latencies.append(
            endpoint.endpoint_decision.classifier_latency_ms
        )
        false_cutoffs += int(endpoint.silence_ms < minimum_delay)
        over_waits += int(endpoint.silence_ms > maximum_delay)

    median_delay = statistics.median(endpoint_delays)
    p95_delay = statistics.quantiles(endpoint_delays, n=20)[18]
    classifier_p95 = statistics.quantiles(classifier_latencies, n=20)[18]
    assert false_cutoffs == 0
    assert over_waits == 0
    assert median_delay <= 600
    assert p95_delay <= 1_400
    assert classifier_p95 < 20


def test_corrected_partial_requires_stability_before_completion():
    model = TranscriptEndpointModel()
    model.update(
        "I want to schedule it tomorrow at ten",
        confidence=0.9,
        stability=0.9,
        language="en",
    )
    model.update(
        "I want to schedule it Friday at ten",
        confidence=0.9,
        stability=0.55,
        language="en",
    )
    decision = model.evaluate(560)
    assert decision.decision == EndpointDecision.UNCERTAIN
    assert decision.reason == "recent_partial_correction_unstable"
    assert decision.recommended_wait_ms >= 700


def test_real_silero_inference_p95_is_below_phase4_budget():
    provider = SileroSpeechProbability()
    for _ in range(5):
        provider.score(FRAME)
    samples = []
    for _ in range(50):
        started = time.perf_counter()
        provider.score(FRAME)
        samples.append((time.perf_counter() - started) * 1_000)
    p95 = statistics.quantiles(samples, n=20)[18]
    assert p95 < 5, f"Silero VAD p95 {p95:.3f}ms exceeds 5ms"
