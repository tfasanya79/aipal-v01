from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EndpointScenario:
    id: str
    language: str
    category: str
    partial_sequence: tuple[str, ...]
    silence_ms: int
    vad_probability: float
    stt_confidence: float
    expected_decision: str
    acceptable_wait_range_ms: tuple[int, int]
    language_confidence: float = 0.96
    code_switching_detected: bool = False


_LANGUAGE_VARIANTS = {
    "en": {
        "names": ["Stephen", "Kelvin", "Amina", "Chidi", "Tunde"],
        "days": ["tomorrow", "Friday", "Monday", "next week", "Wednesday"],
        "times": ["10", "3 pm", "11:30", "8 am", "4:15 pm"],
        "items": ["milk", "bread", "eggs", "soap", "tea"],
        "person": "Stephen",
        "meeting_word": "meeting",
        "reminder_word": "remind me",
        "cancel_word": "cancel it",
        "yes_word": "yes",
        "no_word": "no",
        "stop_word": "stop",
        "complete_question": "What do I have today?",
        "day_question": "What do I have on {day}?",
        "complete_command": "Schedule a meeting with {name} {day} at {time}.",
        "incomplete_command": "Schedule a meeting with {name}",
        "list_start": "Add {a}, {b}, {c}, and",
        "list_end": "Add {a}, {b}, {c}, and {d}.",
        "correction": "Schedule it for {day1}... no, {day2}.",
        "hesitation": "Let me think... {time} works.",
        "date_continuation": "Tomorrow at",
        "time_continuation": "At {time}",
        "person_continuation": "With {name}",
        "code_switch": "Please remind me say I get meeting {day}.",
        "low_confidence": "schedul e mee ting with {name}",
        "unstable": "Schedule a meeting with {name}... actually with {name2}.",
        "noisy": "Schedule the meeting {name} tomorrow",
        "max_duration": "I am still talking but this turn has gone on long enough and should close now.",
    },
    "pcm": {
        "names": ["Emeka", "Ada", "Bola", "Ife", "Musa"],
        "days": ["tomorrow", "Friday", "Monday", "next week", "Wednesday"],
        "times": ["10", "3 pm", "11:30", "8 am", "4:15 pm"],
        "items": ["rice", "beans", "suya", "bread", "water"],
        "person": "Emeka",
        "meeting_word": "meeting",
        "reminder_word": "remind me",
        "cancel_word": "cancel am",
        "yes_word": "yes",
        "no_word": "no",
        "stop_word": "stop am",
        "complete_question": "How my day be today?",
        "day_question": "How my day be for {day}?",
        "complete_command": "Schedule meeting with {name} {day} for {time}.",
        "incomplete_command": "Schedule meeting with {name}",
        "list_start": "Put {a}, {b}, {c}, and",
        "list_end": "Put {a}, {b}, {c}, and {d}.",
        "correction": "Put am for {day1}... no, make it {day2}.",
        "hesitation": "Make I think... {time} go work.",
        "date_continuation": "Tomorrow for",
        "time_continuation": "For {time}",
        "person_continuation": "With {name}",
        "code_switch": "Please remind me say I get meeting {day}.",
        "low_confidence": "schedu l mee ting with {name}",
        "unstable": "Schedule meeting with {name}... actually with {name2}.",
        "noisy": "Schedule the meeting {name} tomorrow",
        "max_duration": "I dey talk too long already and this turn should close now.",
    },
    "fr": {
        "names": ["Awa", "Nina", "Karim", "Sophie", "Moussa"],
        "days": ["demain", "vendredi", "lundi", "la semaine prochaine", "mercredi"],
        "times": ["10h", "15h", "11h30", "8h", "16h15"],
        "items": ["pain", "fromage", "lait", "oeufs", "the"],
        "person": "Awa",
        "meeting_word": "reunion",
        "reminder_word": "rappelle-moi",
        "cancel_word": "annule ca",
        "yes_word": "oui",
        "no_word": "non",
        "stop_word": "arrete",
        "complete_question": "Qu'est-ce que j'ai aujourd'hui ?",
        "day_question": "Qu'est-ce que j'ai {day} ?",
        "complete_command": "Planifie une reunion avec {name} {day} a {time}.",
        "incomplete_command": "Planifie une reunion avec {name}",
        "list_start": "Ajoute {a}, {b}, {c}, et",
        "list_end": "Ajoute {a}, {b}, {c}, et {d}.",
        "correction": "Planifie-le pour {day1}... non, pour {day2}.",
        "hesitation": "Laisse-moi reflechir... {time} convient.",
        "date_continuation": "Demain a",
        "time_continuation": "A {time}",
        "person_continuation": "Avec {name}",
        "code_switch": "Please remind me say I get meeting {day}.",
        "low_confidence": "planifi e une reun ion avec {name}",
        "unstable": "Planifie une reunion avec {name}... en fait avec {name2}.",
        "noisy": "Planifie la reunion {name} demain",
        "max_duration": "Je parle encore mais cette prise doit se fermer maintenant.",
    },
}

_CATEGORY_TARGETS = {
    "complete_statement": ("likely_complete", (380, 720), 0.08, 0.93),
    "incomplete_statement": ("continue_listening", (900, 1400), 0.12, 0.88),
    "complete_question": ("likely_complete", (380, 720), 0.08, 0.94),
    "incomplete_question": ("continue_listening", (900, 1400), 0.12, 0.88),
    "list_continuation": ("continue_listening", (900, 1400), 0.12, 0.84),
    "completed_list": ("likely_complete", (440, 900), 0.08, 0.91),
    "correction": ("likely_complete", (520, 900), 0.10, 0.89),
    "hesitation": ("continue_listening", (900, 1400), 0.12, 0.79),
    "confirmation": ("force_complete", (240, 400), 0.04, 0.97),
    "rejection": ("force_complete", (240, 400), 0.04, 0.96),
    "cancellation": ("force_complete", (240, 400), 0.04, 0.97),
    "short_command": ("force_complete", (200, 380), 0.04, 0.98),
    "date_continuation": ("continue_listening", (900, 1400), 0.12, 0.86),
    "time_continuation": ("continue_listening", (900, 1400), 0.12, 0.86),
    "person_continuation": ("continue_listening", (900, 1400), 0.12, 0.86),
    "code_switching": ("likely_complete", (440, 1200), 0.18, 0.72),
    "low_confidence_transcript": ("uncertain", (900, 1200), 0.24, 0.52),
    "unstable_partial_transcript": ("uncertain", (900, 1200), 0.24, 0.58),
    "noisy_partial_transcript": ("uncertain", (900, 1200), 0.24, 0.56),
    "maximum_duration_completion": ("force_complete", (240, 400), 0.04, 0.98),
}


def _parts(*values: str) -> tuple[str, ...]:
    return tuple(values)


def _scenario(
    *,
    language: str,
    category: str,
    index: int,
    partial_sequence: tuple[str, ...],
    silence_ms: int,
    vad_probability: float,
    stt_confidence: float,
    code_switching_detected: bool = False,
) -> EndpointScenario:
    expected_decision, wait_range, _vad, _stt = _CATEGORY_TARGETS[category]
    return EndpointScenario(
        id=f"{language}-{category}-{index:02d}",
        language=language,
        category=category,
        partial_sequence=partial_sequence,
        silence_ms=silence_ms,
        vad_probability=vad_probability,
        stt_confidence=stt_confidence,
        expected_decision=expected_decision,
        acceptable_wait_range_ms=wait_range,
        language_confidence=0.92 if language != "fr" else 0.95,
        code_switching_detected=code_switching_detected,
    )


def _build_language_cases(language: str) -> list[EndpointScenario]:
    spec = _LANGUAGE_VARIANTS[language]
    names = spec["names"]
    days = spec["days"]
    times = spec["times"]
    items = spec["items"]
    cases: list[EndpointScenario] = []
    for index in range(5):
        name = names[index]
        other_name = names[(index + 1) % len(names)]
        day = days[index]
        other_day = days[(index + 1) % len(days)]
        time = times[index]
        other_time = times[(index + 1) % len(times)]
        item_a = items[index % len(items)]
        item_b = items[(index + 1) % len(items)]
        item_c = items[(index + 2) % len(items)]
        item_d = items[(index + 3) % len(items)]
        cases.extend(
            [
                _scenario(
                    language=language,
                    category="complete_statement",
                    index=index,
                    partial_sequence=_parts(
                        spec["complete_command"].format(name=name, day=day, time=time).split(".")[0],
                        f"{spec['complete_command'].split(' {name} ')[0]} {name}",
                        spec["complete_command"].format(name=name, day=day, time=time),
                    ),
                    silence_ms=420,
                    vad_probability=0.11,
                    stt_confidence=0.94,
                ),
                _scenario(
                    language=language,
                    category="incomplete_statement",
                    index=index,
                    partial_sequence=_parts(
                        f"{spec['incomplete_command'].split(' {name}')[0]} {name}",
                        spec["incomplete_command"].format(name=name),
                    ),
                    silence_ms=1200,
                    vad_probability=0.08,
                    stt_confidence=0.89,
                ),
                _scenario(
                    language=language,
                    category="complete_question",
                    index=index,
                    partial_sequence=_parts(
                        spec["complete_question"].split("?")[0],
                        spec["complete_question"],
                    ),
                    silence_ms=430,
                    vad_probability=0.1,
                    stt_confidence=0.95,
                ),
                _scenario(
                    language=language,
                    category="incomplete_question",
                    index=index,
                    partial_sequence=_parts(
                        spec["day_question"].format(day=day).split("?")[0],
                        f"{spec['day_question'].split('{day}')[0]}{day}".strip(),
                    ),
                    silence_ms=1180,
                    vad_probability=0.1,
                    stt_confidence=0.87,
                ),
                _scenario(
                    language=language,
                    category="list_continuation",
                    index=index,
                    partial_sequence=_parts(
                        f"{spec['list_start'].format(a=item_a, b=item_b, c=item_c).rstrip('and ').rstrip(', ')}",
                        spec["list_start"].format(a=item_a, b=item_b, c=item_c).rstrip(),
                    ),
                    silence_ms=1120,
                    vad_probability=0.12,
                    stt_confidence=0.84,
                ),
                _scenario(
                    language=language,
                    category="completed_list",
                    index=index,
                    partial_sequence=_parts(
                        spec["list_end"].format(a=item_a, b=item_b, c=item_c, d=item_d).rstrip("."),
                        spec["list_end"].format(a=item_a, b=item_b, c=item_c, d=item_d),
                    ),
                    silence_ms=500,
                    vad_probability=0.12,
                    stt_confidence=0.92,
                ),
                _scenario(
                    language=language,
                    category="correction",
                    index=index,
                    partial_sequence=_parts(
                        spec["correction"].format(day1=day, day2=other_day).split("...")[0],
                        spec["correction"].format(day1=day, day2=other_day),
                    ),
                    silence_ms=620,
                    vad_probability=0.11,
                    stt_confidence=0.91,
                ),
                _scenario(
                    language=language,
                    category="hesitation",
                    index=index,
                    partial_sequence=_parts(
                        spec["hesitation"].split("...")[0],
                        spec["hesitation"].split("...")[0] + "...",
                    ),
                    silence_ms=980,
                    vad_probability=0.14,
                    stt_confidence=0.8,
                ),
                _scenario(
                    language=language,
                    category="confirmation",
                    index=index,
                    partial_sequence=_parts(spec["yes_word"], spec["yes_word"]),
                    silence_ms=260,
                    vad_probability=0.06,
                    stt_confidence=0.97,
                ),
                _scenario(
                    language=language,
                    category="rejection",
                    index=index,
                    partial_sequence=_parts(spec["no_word"], spec["no_word"]),
                    silence_ms=260,
                    vad_probability=0.06,
                    stt_confidence=0.96,
                ),
                _scenario(
                    language=language,
                    category="cancellation",
                    index=index,
                    partial_sequence=_parts(spec["cancel_word"], spec["cancel_word"]),
                    silence_ms=260,
                    vad_probability=0.06,
                    stt_confidence=0.97,
                ),
                _scenario(
                    language=language,
                    category="short_command",
                    index=index,
                    partial_sequence=_parts(spec["stop_word"], spec["stop_word"]),
                    silence_ms=220,
                    vad_probability=0.05,
                    stt_confidence=0.98,
                ),
                _scenario(
                    language=language,
                    category="date_continuation",
                    index=index,
                    partial_sequence=_parts(
                        f"{spec['date_continuation']} {day}",
                        f"{spec['date_continuation']} {day} {time}",
                    ),
                    silence_ms=1160,
                    vad_probability=0.1,
                    stt_confidence=0.86,
                ),
                _scenario(
                    language=language,
                    category="time_continuation",
                    index=index,
                    partial_sequence=_parts(
                        f"{spec['time_continuation'].format(time=time)}",
                        f"{spec['time_continuation'].format(time=time)} {other_time}",
                    ),
                    silence_ms=1160,
                    vad_probability=0.1,
                    stt_confidence=0.86,
                ),
                _scenario(
                    language=language,
                    category="person_continuation",
                    index=index,
                    partial_sequence=_parts(
                        f"{spec['person_continuation'].format(name=name)}",
                        f"{spec['person_continuation'].format(name=name)} {other_name}",
                    ),
                    silence_ms=1160,
                    vad_probability=0.1,
                    stt_confidence=0.86,
                ),
                _scenario(
                    language=language,
                    category="code_switching",
                    index=index,
                    partial_sequence=_parts(
                        spec["code_switch"].format(day=day),
                        spec["code_switch"].format(day=day) + f" {time}",
                    ),
                    silence_ms=760,
                    vad_probability=0.18,
                    stt_confidence=0.74,
                    code_switching_detected=True,
                ),
                _scenario(
                    language=language,
                    category="low_confidence_transcript",
                    index=index,
                    partial_sequence=_parts(
                        spec["low_confidence"].format(name=name),
                        spec["low_confidence"].format(name=name) + " " + other_name,
                    ),
                    silence_ms=1080,
                    vad_probability=0.22,
                    stt_confidence=0.49,
                ),
                _scenario(
                    language=language,
                    category="unstable_partial_transcript",
                    index=index,
                    partial_sequence=_parts(
                        spec["unstable"].format(name=name, name2=other_name),
                        spec["unstable"].format(name=name, name2=other_name) + " " + day,
                    ),
                    silence_ms=1040,
                    vad_probability=0.18,
                    stt_confidence=0.59,
                ),
                _scenario(
                    language=language,
                    category="noisy_partial_transcript",
                    index=index,
                    partial_sequence=_parts(
                        spec["noisy"].format(name=name),
                        spec["noisy"].format(name=name) + " " + time,
                    ),
                    silence_ms=1080,
                    vad_probability=0.24,
                    stt_confidence=0.57,
                ),
                _scenario(
                    language=language,
                    category="maximum_duration_completion",
                    index=index,
                    partial_sequence=_parts(
                        spec["max_duration"],
                        spec["max_duration"] + f" {name}",
                    ),
                    silence_ms=1800,
                    vad_probability=0.14,
                    stt_confidence=0.91,
                ),
            ]
        )
    return cases


def build_endpoint_regression_corpus() -> list[EndpointScenario]:
    corpus: list[EndpointScenario] = []
    for language in ("en", "pcm", "fr"):
        corpus.extend(_build_language_cases(language))
    return corpus
