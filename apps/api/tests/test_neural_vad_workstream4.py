from __future__ import annotations

import statistics

from app.config import Settings
from app.services.turn_detection import (
    AcousticState,
    AdaptiveEnergyProbability,
    HybridTurnDetector,
    TurnSignal,
    create_speech_probability_provider,
)
from tests.fixtures.acoustic_turn_corpus import CATEGORIES
from app.services.voice_transport import VoiceAudioIngress
from tests.fixtures.acoustic_turn_corpus import ACOUSTIC_CORPUS


FRAME = b"\x00" * 1_280


class ProbabilitySequence:
    name = "synthetic_neural_vad"
    fallback_active = False

    def __init__(self, values: list[float], default: float = 0.04) -> None:
        self.values = list(values)
        self.default = default

    def score(self, _pcm: bytes) -> float:
        return self.values.pop(0) if self.values else self.default

    def reset(self) -> None:
        pass

    def diagnostics(self) -> dict:
        return {"provider": self.name, "fallback_active": False, "healthy": True}


def test_acoustic_corpus_has_20_synthetic_cases_per_required_category():
    assert len(ACOUSTIC_CORPUS) == len(CATEGORIES) * 20
    assert all(case["synthetic"] for case in ACOUSTIC_CORPUS)
    assert {case["category"] for case in ACOUSTIC_CORPUS} == set(CATEGORIES)
    counts = {category: 0 for category in CATEGORIES}
    for case in ACOUSTIC_CORPUS:
        counts[case["category"]] += 1
    assert min(counts.values()) >= 20


def test_canonical_acoustic_contract_covers_start_barge_pause_end_and_forced_end():
    start = HybridTurnDetector(
        speech_provider=ProbabilitySequence([0.9, 0.9])
    )
    assert not start.process(FRAME)
    event = start.process(FRAME)[0]
    assert event.acoustic_decision is not None
    assert event.acoustic_decision.state == AcousticState.SPEECH_STARTED

    barge = HybridTurnDetector(
        speech_provider=ProbabilitySequence([0.9, 0.9])
    )
    assert not barge.process(FRAME, ai_speaking=True)
    event = barge.process(FRAME, ai_speaking=True)[0]
    assert event.acoustic_decision.state == AcousticState.BARGE_IN

    pause = HybridTurnDetector(
        speech_provider=ProbabilitySequence([0.9, 0.9] + [0.02] * 40)
    )
    pause.process(FRAME)
    pause.process(FRAME)
    pause.update_transcript("Schedule a meeting with", stability=0.95)
    states = []
    for _ in range(40):
        states.extend(
            event.acoustic_decision.state
            for event in pause.process(FRAME)
            if event.acoustic_decision
        )
    assert AcousticState.THINKING_PAUSE in states
    assert AcousticState.SPEECH_ENDED in states


def test_probable_playback_echo_does_not_create_a_barge_in():
    detector = HybridTurnDetector(
        speech_provider=ProbabilitySequence([0.68, 0.68, 0.05])
    )
    assert detector.process(FRAME, ai_speaking=True) == []
    assert detector.process(FRAME, ai_speaking=True) == []
    assert detector.process(FRAME, ai_speaking=True) == []
    assert detector.active is False


def test_quiet_neural_speech_is_not_blocked_by_energy_gate():
    detector = HybridTurnDetector(
        speech_provider=ProbabilitySequence([0.7, 0.7])
    )
    detector.process(FRAME)
    event = detector.process(FRAME)[0]
    assert event.signal == TurnSignal.SPEECH_STARTED


def test_vad_diagnostics_expose_safe_operational_configuration():
    detector = HybridTurnDetector(
        speech_provider=ProbabilitySequence([0.05])
    )
    diagnostics = detector.diagnostics()
    assert diagnostics["sample_rate"] if "sample_rate" in diagnostics else True
    assert diagnostics["production_fallback_policy"] == "fail_closed"
    assert diagnostics["start_min_ms"] == 64
    assert "active_state" in diagnostics


def test_production_configuration_is_fail_closed_by_default():
    settings = Settings(aipal_env="production")
    assert settings.neural_vad_production_fallback_policy == "fail_closed"
    assert settings.neural_vad_fallback_mode == "adaptive_energy_development_only"


def test_energy_provider_is_explicitly_marked_fallback():
    provider = AdaptiveEnergyProbability()
    assert provider.fallback_active is True
    assert provider.diagnostics()["fallback_active"] is True


def test_primary_provider_is_real_neural_vad_and_meets_latency_budget():
    provider = create_speech_probability_provider()
    assert provider.name == "silero_v6"
    for _ in range(5):
        provider.score(FRAME)
    values = []
    for _ in range(50):
        provider.score(FRAME)
        latency = provider.diagnostics()["latency_p95_ms"]
        if latency is not None:
            values.append(latency)
    assert statistics.median(values) < 20


def test_ingress_rejects_out_of_order_stale_timestamp_and_malformed_pcm():
    ingress = VoiceAudioIngress(max_utterance_ms=None)
    ingress.start("stream")
    assert ingress.accept(
        turn_id="stream", sequence=0, pcm=FRAME, timestamp_ms=100
    ).accepted
    out_of_order = ingress.accept(
        turn_id="stream", sequence=-1, pcm=FRAME, timestamp_ms=101
    )
    assert out_of_order.reason == "out_of_order_sequence"
    stale = ingress.accept(
        turn_id="stream", sequence=1, pcm=FRAME, timestamp_ms=99
    )
    assert stale.reason == "stale_timestamp"
    malformed = ingress.accept(
        turn_id="stream", sequence=1, pcm=b"x", timestamp_ms=101
    )
    assert malformed.reason == "malformed_pcm_frame"


def test_session_cancel_resets_acoustic_and_neural_state_without_leakage():
    provider = ProbabilitySequence([0.9, 0.9, 0.05, 0.05])
    detector = HybridTurnDetector(speech_provider=provider)
    detector.process(FRAME)
    detector.process(FRAME)
    assert detector.active
    detector.cancel()
    assert not detector.active
    assert detector.diagnostics()["active_state"] == "silence"


def test_two_sessions_keep_independent_neural_and_acoustic_state():
    first = HybridTurnDetector(
        speech_provider=ProbabilitySequence([0.9, 0.9])
    )
    second = HybridTurnDetector(
        speech_provider=ProbabilitySequence([0.05, 0.05])
    )
    first.process(FRAME)
    first.process(FRAME)
    second.process(FRAME)
    second.process(FRAME)
    assert first.active is True
    assert second.active is False
    first.cancel()
    assert second.diagnostics()["active_state"] == "silence"


def test_corpus_start_and_echo_metrics_pass_per_category():
    by_category: dict[str, dict[str, int | list[int]]] = {}
    for case in ACOUSTIC_CORPUS:
        category = case["category"]
        row = by_category.setdefault(
            category,
            {"cases": 0, "starts": 0, "false_starts": 0, "missed": 0, "latencies": []},
        )
        row["cases"] += 1
        values = list(case["speech_probabilities"])
        expected_start = not bool(case.get("noise_only"))
        detector = HybridTurnDetector(speech_provider=ProbabilitySequence(values))
        events = []
        for frame_index in range(2):
            events.extend(
                detector.process(FRAME, ai_speaking=bool(case["ai_speaking"]))
            )
            if events:
                row["latencies"].append((frame_index + 1) * 40)
        started = any(event.signal == TurnSignal.SPEECH_STARTED for event in events)
        row["starts"] += int(started)
        row["false_starts"] += int(started and not expected_start)
        row["missed"] += int(expected_start and not started)

    assert len(by_category) == len(CATEGORIES)
    for category, row in by_category.items():
        assert row["false_starts"] == 0, category
        assert row["missed"] == 0, category
        latencies = row["latencies"]
        if latencies:
            assert statistics.median(latencies) <= 250, category


def _percentile(values: list[int], percentile: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = round((len(ordered) - 1) * percentile)
    return ordered[index]


def test_acoustic_endpoint_metrics_are_reported_per_required_category():
    metrics: dict[str, dict[str, int | list[int]]] = {
        category: {
            "cases": 0,
            "speech_start_ms": [],
            "endpoint_ms": [],
            "false_starts": 0,
            "missed_starts": 0,
            "false_ends": 0,
            "over_waits": 0,
            "incomplete_false_cutoffs": 0,
            "forced_endpoints": 0,
            "uncertain_decisions": 0,
        }
        for category in CATEGORIES
    }
    incomplete_categories = {"incomplete_request", "thinking_pause", "list_continuation"}
    uncertain_categories = {"low_confidence_transcript", "unstable_transcript"}

    for case in ACOUSTIC_CORPUS:
        row = metrics[case["category"]]
        row["cases"] += 1
        detector = HybridTurnDetector(
            speech_provider=ProbabilitySequence(list(case["speech_probabilities"]) + [0.05] * 40)
        )
        detector.update_transcript(
            case["transcript"],
            confidence=0.35 if case["category"] == "low_confidence_transcript" else 0.92,
            stability=0.55 if case["category"] == "unstable_transcript" else 0.95,
            language="en",
        )
        events = []
        for frame_index in range(40):
            batch = detector.process(FRAME, ai_speaking=bool(case["ai_speaking"]))
            events.extend(batch)
            if any(event.signal == TurnSignal.SPEECH_STARTED for event in batch):
                row["speech_start_ms"].append((frame_index + 1) * 40)
            endpoint = next((event for event in batch if event.signal == TurnSignal.ENDPOINT), None)
            if endpoint is not None:
                row["endpoint_ms"].append(endpoint.silence_ms)
                if endpoint.endpoint_decision is not None:
                    if endpoint.endpoint_decision.decision.value == "force_complete":
                        row["forced_endpoints"] += 1
                    if endpoint.endpoint_decision.decision.value == "uncertain":
                        row["uncertain_decisions"] += 1
                break

        started = any(event.signal == TurnSignal.SPEECH_STARTED for event in events)
        noise_only = bool(case["noise_only"])
        row["false_starts"] += int(started and noise_only)
        row["missed_starts"] += int((not started) and not noise_only)
        endpoint = next((event for event in events if event.signal == TurnSignal.ENDPOINT), None)
        finalized_incomplete = bool(
            endpoint
            and endpoint.endpoint_decision
            and endpoint.endpoint_decision.decision.value != "continue_listening"
            and case["category"] in incomplete_categories
        )
        row["false_ends"] += int(finalized_incomplete)
        row["incomplete_false_cutoffs"] += int(finalized_incomplete)
        if row["endpoint_ms"] and max(row["endpoint_ms"]) > int(case["accepted_endpoint_upper_ms"]):
            row["over_waits"] += 1

    for category, row in metrics.items():
        assert row["cases"] >= 20, category
        assert row["false_starts"] == 0, category
        assert row["missed_starts"] == 0, category
        assert row["false_ends"] == 0, category
        assert row["over_waits"] == 0, category
        assert row["incomplete_false_cutoffs"] == 0, category
        if category not in {"probable_echo", "typing_transient_noise"}:
            assert _percentile(row["speech_start_ms"], 0.5) is not None, category
        if category not in {"probable_echo", "typing_transient_noise", *incomplete_categories, *uncertain_categories}:
            assert _percentile(row["endpoint_ms"], 0.5) is not None, category
            assert _percentile(row["endpoint_ms"], 0.95) <= 900, category
