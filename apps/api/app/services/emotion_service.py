from __future__ import annotations

try:  # pragma: no cover - optional dependency fallback
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

    _analyzer = SentimentIntensityAnalyzer()
except Exception:  # pragma: no cover
    _analyzer = None


def detect_emotion(message: str) -> dict[str, object]:
    text = (message or "").strip().lower()
    compound = 0.0
    if _analyzer is not None:
        scores = _analyzer.polarity_scores(text)
        compound = scores["compound"]
    else:
        if any(word in text for word in ("great", "good", "happy", "excited", "proud")):
            compound = 0.6
        elif any(word in text for word in ("sad", "bad", "angry", "frustrated", "worried", "tired")):
            compound = -0.6
    intensity = max(1, min(10, int(round(abs(compound) * 10)) or 1))

    if any(word in text for word in ("burned out", "burnt out", "exhausted", "drained", "tired")):
        emotion = "burned_out"
    elif any(word in text for word in ("worried", "anxious", "nervous", "stressed", "stress")):
        emotion = "anxious"
    elif any(word in text for word in ("frustrated", "annoyed", "angry", "mad")) or compound <= -0.45:
        emotion = "frustrated"
    elif any(word in text for word in ("sad", "down", "low", "lonely", "hurt")):
        emotion = "sad"
    elif any(word in text for word in ("excited", "great", "amazing", "happy", "proud")) or compound >= 0.55:
        emotion = "excited" if "excited" in text or compound >= 0.7 else "happy"
    elif "confused" in text or "unsure" in text or "not sure" in text or "stuck" in text:
        emotion = "confused"
    else:
        emotion = "neutral"

    context = "Sentiment appears positive." if compound > 0.2 else "Sentiment appears negative." if compound < -0.2 else "Sentiment is neutral or mixed."
    if emotion in {"burned_out", "anxious", "frustrated", "sad", "confused"}:
        context = "The user may need empathy, clarity, or gentle guidance."

    return {"emotion": emotion, "intensity": intensity, "context": context}
