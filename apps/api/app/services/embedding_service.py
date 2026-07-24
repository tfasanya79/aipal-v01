from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import re
import threading
from collections.abc import Awaitable, Callable

import httpx

from ..config import get_settings

_DIM = 1536
log = logging.getLogger("aipal.embeddings")
_fastembed_model = None
_fastembed_model_name: str | None = None
_fastembed_lock = threading.Lock()
_fallback_logged = False


def embed_text(text: str, *, dim: int = _DIM) -> list[float]:
    """Deterministic lightweight embedding for semantic retrieval."""
    vec = [0.0] * dim
    tokens = re.findall(r"[a-z0-9']+", (text or "").lower())
    if not tokens:
        return vec

    for idx, token in enumerate(tokens):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % dim
        weight = 1.0 + (idx % 5) * 0.05
        vec[bucket] += weight
        vec[(bucket * 7 + 13) % dim] += weight * 0.35

    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine_similarity(left: list[float] | None, right: list[float] | None) -> float:
    if not left or not right:
        return 0.0
    size = min(len(left), len(right))
    dot = sum(left[i] * right[i] for i in range(size))
    lnorm = math.sqrt(sum(v * v for v in left[:size])) or 1.0
    rnorm = math.sqrt(sum(v * v for v in right[:size])) or 1.0
    return dot / (lnorm * rnorm)


def normalize_embedding(values: list[float], *, dim: int = _DIM) -> list[float]:
    """Normalize provider vectors to the database's fixed vector dimension."""
    vector = [float(value) for value in values[:dim]]
    if len(vector) < dim:
        vector.extend([0.0] * (dim - len(vector)))
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def embed_texts_local(texts: list[str], model_name: str) -> list[list[float]]:
    """Embed a bounded batch with the shared local semantic model."""
    global _fastembed_model, _fastembed_model_name
    with _fastembed_lock:
        if _fastembed_model is None or _fastembed_model_name != model_name:
            from fastembed import TextEmbedding

            _fastembed_model = TextEmbedding(model_name=model_name)
            _fastembed_model_name = model_name
        rows = list(_fastembed_model.embed(texts))
    return [normalize_embedding(list(row)) for row in rows]


def embed_text_local(text: str, model_name: str) -> list[float]:
    return embed_texts_local([text], model_name)[0]


async def embed_text_semantic(text: str) -> list[float]:
    """Create a real semantic embedding, with an explicit development fallback.

    Production supports local FastEmbed, OpenAI-compatible embeddings, and
    Ollama. The deterministic fallback keeps offline development and tests
    functional but is logged because it is not a production semantic model.
    """
    global _fallback_logged
    settings = get_settings()
    provider = settings.embedding_provider.strip().lower()
    clean = (text or "").strip()
    if not clean:
        return [0.0] * _DIM

    try:
        if provider == "fastembed":
            return await asyncio.wait_for(
                asyncio.to_thread(embed_text_local, clean, settings.embedding_model),
                timeout=settings.embedding_timeout_seconds,
            )
        if provider == "openai":
            if not settings.openai_api_key:
                raise RuntimeError("OPENAI_API_KEY is required for the OpenAI embedding provider")
            async with httpx.AsyncClient(timeout=settings.embedding_timeout_seconds) as client:
                response = await client.post(
                    f"{settings.openai_base_url.rstrip('/')}/embeddings",
                    headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                    json={"model": settings.embedding_model, "input": clean},
                )
                response.raise_for_status()
                return normalize_embedding(response.json()["data"][0]["embedding"])
        if provider == "ollama":
            async with httpx.AsyncClient(timeout=settings.embedding_timeout_seconds) as client:
                response = await client.post(
                    f"{settings.ollama_base_url.rstrip('/')}/api/embed",
                    json={"model": settings.embedding_model, "input": clean},
                )
                response.raise_for_status()
                return normalize_embedding(response.json()["embeddings"][0])
        if provider != "deterministic":
            raise ValueError(f"Unsupported embedding provider: {provider}")
    except Exception as exc:
        if settings.aipal_env.lower() in {"production", "prod"}:
            raise RuntimeError(f"Semantic embedding provider '{provider}' failed") from exc
        if not _fallback_logged:
            log.warning("semantic embedding unavailable; using development fallback: %s", exc)
            _fallback_logged = True
    return embed_text(clean)


EmbeddingFunction = Callable[[str], Awaitable[list[float]]]
