"""Synthetic Workstream 4 acoustic regression corpus (320 reproducible cases).

These fixtures model neural probabilities and transport conditions. They are not
recordings and must not be represented as physical-device validation.
"""

from __future__ import annotations

CATEGORIES = (
    "clean_complete_speech",
    "quiet_complete_speech",
    "loud_complete_speech",
    "short_command",
    "incomplete_request",
    "thinking_pause",
    "correction",
    "list_continuation",
    "low_confidence_transcript",
    "unstable_transcript",
    "fan_noise_during_speech",
    "traffic_noise_during_speech",
    "packet_gap",
    "route_change",
    "probable_echo",
    "genuine_barge_in",
    "typing_transient_noise",
)

CONDITIONS = tuple(f"variant_{index:02d}" for index in range(20))

_BASE_PROBABILITY = {
    "quiet_complete_speech": 0.72,
    "loud_complete_speech": 0.96,
    "fan_noise_during_speech": 0.79,
    "traffic_noise_during_speech": 0.81,
    "packet_gap": 0.88,
    "route_change": 0.83,
    "probable_echo": 0.68,
    "typing_transient_noise": 0.32,
}

_TRANSCRIPTS = {
    "clean_complete_speech": "Schedule a meeting with Stephen tomorrow at 10.",
    "quiet_complete_speech": "Remind me to call Stephen tomorrow.",
    "loud_complete_speech": "What do I have today?",
    "short_command": "Stop",
    "incomplete_request": "Schedule a meeting with Stephen…",
    "thinking_pause": "My meeting is at… give me a second…",
    "correction": "I want to… actually, make that Friday.",
    "list_continuation": "Add milk, bread, eggs, and",
    "low_confidence_transcript": "Schedule uh meeting Stephen tom",
    "unstable_transcript": "I want to schedule it Friday at",
    "fan_noise_during_speech": "Add soap to my shopping list.",
    "traffic_noise_during_speech": "When is my next meeting?",
    "packet_gap": "Book a call with Kelvin on Friday at three.",
    "route_change": "Show my calendar for tomorrow.",
    "probable_echo": "",
    "genuine_barge_in": "Stop",
    "typing_transient_noise": "",
}

_EXPECTED_DECISION = {
    "incomplete_request": "continue_listening",
    "thinking_pause": "continue_listening",
    "list_continuation": "continue_listening",
    "low_confidence_transcript": "uncertain",
    "unstable_transcript": "uncertain",
}


def build_acoustic_corpus() -> list[dict]:
    cases: list[dict] = []
    for category in CATEGORIES:
        for variant, condition_name in enumerate(CONDITIONS):
            speech_probability = _BASE_PROBABILITY.get(category, 0.90)
            speech_probability = max(0.0, min(0.99, speech_probability + ((variant % 5) - 2) * 0.01))
            noise_probability = 0.04 + (variant % 4) * 0.03
            ai_speaking = category in {"genuine_barge_in", "probable_echo"}
            is_noise_only = category in {"probable_echo", "typing_transient_noise"}
            expected_state = {
                "genuine_barge_in": "barge_in",
                "probable_echo": "silence",
                "typing_transient_noise": "silence",
                "thinking_pause": "thinking_pause",
                "incomplete_request": "thinking_pause",
                "list_continuation": "thinking_pause",
            }.get(category, "speech_started")
            cases.append(
                {
                    "id": f"acoustic-{len(cases) + 1:03d}",
                    "category": category,
                    "condition": condition_name,
                    "speech_probabilities": (
                        [noise_probability, noise_probability]
                        if is_noise_only
                        else [speech_probability, speech_probability]
                    ),
                    "noise_probability": noise_probability,
                    "ai_speaking": ai_speaking,
                    "expected_state": expected_state,
                    "expected_decision": _EXPECTED_DECISION.get(category, "likely_complete"),
                    "transcript": _TRANSCRIPTS[category],
                    "synthetic": True,
                    "sample_rate": 16_000,
                    "frame_ms": 40,
                    "accepted_endpoint_upper_ms": 1_400 if category in _EXPECTED_DECISION else 900,
                    "noise_only": is_noise_only,
                }
            )
    return cases


ACOUSTIC_CORPUS = build_acoustic_corpus()
