"""Download and validate the configured semantic embedding model at deploy time."""

from __future__ import annotations

import asyncio
import math
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


async def main() -> None:
    from app.config import get_settings
    from app.services.embedding_service import embed_text_semantic
    from app.services.turn_detection import EndpointContext, create_semantic_endpoint_classifier
    from app.conversation.topic_transition import get_topic_classifier

    settings = get_settings()
    vector = await embed_text_semantic("AiPal semantic memory deployment check")
    norm = math.sqrt(sum(value * value for value in vector))
    if len(vector) != 1536 or not math.isfinite(norm) or norm <= 0:
        raise RuntimeError("Embedding model returned an invalid 1536-dimensional vector")
    endpoint_classifier = create_semantic_endpoint_classifier()
    if endpoint_classifier.fallback_active:
        raise RuntimeError(
            "Semantic endpointing model is unavailable; fallback cannot pass preload"
        )
    probe = endpoint_classifier.classify(
        "Schedule a meeting tomorrow at ten",
        EndpointContext(detected_language="en", languages=("en",)),
    )
    if not probe.label or not 0 <= probe.confidence <= 1:
        raise RuntimeError("Semantic endpointing model returned a malformed result")
    topic_classifier = get_topic_classifier()
    if topic_classifier.fallback_active:
        raise RuntimeError("Semantic topic classifier is unavailable")
    similarities = topic_classifier.similarities(
        "Make it Friday instead",
        ["Schedule a meeting with Stephen tomorrow"],
    )
    if len(similarities) != 3 or any(not -1 <= value <= 1 for value in similarities):
        raise RuntimeError("Semantic topic classifier returned a malformed result")
    print(
        "embedding model ready "
        f"provider={settings.embedding_provider} model={settings.embedding_model} "
        f"dimensions={len(vector)} endpointing={endpoint_classifier.name} "
        f"endpoint_model={getattr(endpoint_classifier, 'model_name', 'unknown')} "
        f"topic_classifier={topic_classifier.provider}"
    )


if __name__ == "__main__":
    asyncio.run(main())
