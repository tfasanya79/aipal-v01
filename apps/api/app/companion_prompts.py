"""Warm companion copy for Live mode and prompts."""

import random

STARTER_LINES = [
    "Hi {name}, I am here with you. How are you feeling right now?",
    "Welcome back, {name}. Would you like a quick check-in, or a calm moment first?",
    "Hey {name}, I am listening. What feels most present for you right now?",
    "{name}, I am glad you are here. What would feel most helpful to talk through?",
]


def pick_starter(wake_name: str | None) -> str:
    name = (wake_name or "friend").strip() or "friend"
    line = random.choice(STARTER_LINES)
    return line.format(name=name)
