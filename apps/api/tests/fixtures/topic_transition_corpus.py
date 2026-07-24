from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TopicScenario:
    id: str
    language: str
    classification: str
    utterance: str
    active_similarity: float
    paused_similarity: float = 0.0
    pending: bool = False
    missing: str | None = None
    active_entities: tuple[tuple[str, str], ...] = ()
    paused_topic: bool = False


_DISTRIBUTION = {
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
_LANGUAGES = ("en", "en-NG", "pcm", "en-pcm", "fr")


def build_topic_transition_corpus() -> list[TopicScenario]:
    rows: list[TopicScenario] = []
    for classification, count in _DISTRIBUTION.items():
        for index in range(count):
            language = _LANGUAGES[index % len(_LANGUAGES)]
            values = _values(classification, index)
            rows.append(
                TopicScenario(
                    id=f"topic-{classification}-{index:03d}",
                    language=language,
                    classification=classification,
                    **values,
                )
            )
    return rows


def _values(classification: str, index: int) -> dict:
    hour = 10 + index % 8
    if classification == "continue_same_topic":
        return {"utterance": f"{hour}:00", "active_similarity": 0.82, "pending": True, "missing": "time"}
    if classification == "refine_current_request":
        return {"utterance": f"Add the time {hour}:00", "active_similarity": 0.82}
    if classification == "modify_active_request":
        return {"utterance": f"Make it {hour}:00", "active_similarity": 0.8, "pending": True, "active_entities": (("time", "09:00"),)}
    if classification == "correct_previous_detail":
        return {"utterance": f"Sorry, I meant {hour}:00", "active_similarity": 0.72, "active_entities": (("time", "09:00"),)}
    if classification == "add_related_request":
        return {"utterance": "And also remind me to call Stephen", "active_similarity": 0.68}
    if classification == "new_related_subtopic":
        return {"utterance": "What should the pilot sales team do next?", "active_similarity": 0.5}
    if classification == "new_unrelated_topic":
        return {"utterance": "What is the weather for my holiday flight?", "active_similarity": 0.1, "pending": True}
    if classification == "resume_previous_topic":
        return {"utterance": "Back to the Qring pilot", "active_similarity": 0.18, "paused_similarity": 0.82, "paused_topic": True}
    if classification == "cancel_active_request":
        return {"utterance": "Never mind", "active_similarity": 0.0, "pending": True}
    return {"utterance": "Change it", "active_similarity": 0.35, "paused_similarity": 0.34, "paused_topic": True}
