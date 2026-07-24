import json
import logging
from collections.abc import AsyncIterator
import httpx

from .config import get_settings
from .services.prompt_builder import CANONICAL_PROMPT_MARKER

log = logging.getLogger("aipal.llm")
settings = get_settings()

async def llm_chat(
    messages: list[dict[str, str]],
    *,
    max_tokens: int | None = None,
    timeout_seconds: float | None = None,
    response_schema: dict | None = None,
) -> str:
    messages = _validated_messages(messages)
    provider = settings.llm_provider.lower()
    try:
        if provider in {"openai", "openai_compatible"} and settings.openai_api_key:
            return await _openai_chat(
                messages,
                max_tokens=max_tokens,
                timeout_seconds=timeout_seconds,
                response_schema=response_schema,
            )
        if provider == "deepseek" and settings.deepseek_api_key:
            return await _deepseek_chat(
                messages,
                max_tokens=max_tokens,
                timeout_seconds=timeout_seconds,
                response_schema=response_schema,
            )
        return await _ollama_chat(
            messages,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
            response_schema=response_schema,
        )
    except (httpx.HTTPError, OSError) as exc:
        log.exception("LLM provider unavailable")
        raise RuntimeError("LLM provider unavailable") from exc


async def llm_chat_stream(
    messages: list[dict[str, str]],
    *,
    max_tokens: int | None = None,
    timeout_seconds: float | None = None,
) -> AsyncIterator[str]:
    messages = _validated_messages(messages)
    provider = settings.llm_provider.lower()
    try:
        if provider in {"openai", "openai_compatible"} and settings.openai_api_key:
            async for chunk in _openai_chat_stream(
                messages,
                max_tokens=max_tokens,
                timeout_seconds=timeout_seconds,
            ):
                yield chunk
            return
        if provider == "deepseek" and settings.deepseek_api_key:
            async for chunk in _deepseek_chat_stream(
                messages,
                max_tokens=max_tokens,
                timeout_seconds=timeout_seconds,
            ):
                yield chunk
            return
        async for chunk in _ollama_chat_stream(
            messages,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
        ):
            yield chunk
    except (httpx.HTTPError, OSError) as exc:
        log.exception("Streaming LLM provider unavailable")
        raise RuntimeError("Streaming LLM provider unavailable") from exc
async def _deepseek_chat(
    messages: list[dict[str, str]],
    *,
    max_tokens: int | None = None,
    timeout_seconds: float | None = None,
    response_schema: dict | None = None,
) -> str:
    async with httpx.AsyncClient(
        timeout=timeout_seconds or settings.deepseek_timeout_seconds
    ) as client:
        payload = {
            "model": "deepseek-chat",
            "messages": messages,
            "max_tokens": max_tokens or settings.deepseek_max_tokens,
            "temperature": 0.25,
        }
        if response_schema is not None:
            payload["response_format"] = {"type": "json_object"}
        resp = await client.post(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


async def _deepseek_chat_stream(
    messages: list[dict[str, str]],
    *,
    max_tokens: int | None = None,
    timeout_seconds: float | None = None,
) -> AsyncIterator[str]:
    async with httpx.AsyncClient(
        timeout=timeout_seconds or settings.deepseek_timeout_seconds
    ) as client:
        async with client.stream(
            "POST",
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
            json={
                "model": "deepseek-chat",
                "messages": messages,
                "max_tokens": max_tokens or settings.deepseek_max_tokens,
                "temperature": 0.25,
                "stream": True,
            },
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[6:].strip()
                if payload == "[DONE]":
                    break
                try:
                    data = json.loads(payload)
                    delta = data["choices"][0].get("delta", {}).get("content")
                    if delta:
                        yield delta
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue


async def _openai_chat(
    messages: list[dict[str, str]],
    *,
    max_tokens: int | None = None,
    timeout_seconds: float | None = None,
    response_schema: dict | None = None,
) -> str:
    async with httpx.AsyncClient(
        timeout=timeout_seconds or settings.openai_timeout_seconds
    ) as client:
        payload = {
            "model": settings.openai_model,
            "messages": messages,
            "max_tokens": max_tokens or settings.openai_max_tokens,
        }
        if response_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "aipal_reasoning_decision",
                    "strict": True,
                    "schema": response_schema,
                },
            }
        resp = await client.post(
            f"{settings.openai_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


async def _openai_chat_stream(
    messages: list[dict[str, str]],
    *,
    max_tokens: int | None = None,
    timeout_seconds: float | None = None,
) -> AsyncIterator[str]:
    async with httpx.AsyncClient(
        timeout=timeout_seconds or settings.openai_timeout_seconds
    ) as client:
        async with client.stream(
            "POST",
            f"{settings.openai_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={
                "model": settings.openai_model,
                "messages": messages,
                "max_tokens": max_tokens or settings.openai_max_tokens,
                "stream": True,
            },
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[6:].strip()
                if payload == "[DONE]":
                    break
                try:
                    data = json.loads(payload)
                    delta = data["choices"][0].get("delta", {}).get("content")
                    if delta:
                        yield delta
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue


async def llm_chat_json(messages: list[dict[str, str]]) -> dict:
    import re

    text = await llm_chat(messages)
    text = text.strip()
    if m := re.search(r"\{[\s\S]*\}", text):
        text = m.group(0)
    return json.loads(text)


async def _ollama_chat(
    messages: list[dict[str, str]],
    *,
    max_tokens: int | None = None,
    timeout_seconds: float | None = None,
    response_schema: dict | None = None,
) -> str:
    async with httpx.AsyncClient(
        timeout=timeout_seconds or settings.ollama_timeout_seconds
    ) as client:
        payload = {
            "model": settings.ollama_model,
            "messages": messages,
            "stream": False,
            "options": {
                "num_predict": max_tokens or max(48, settings.ollama_num_predict),
                "temperature": settings.ollama_temperature,
            },
        }
        if response_schema is not None:
            payload["format"] = response_schema
        resp = await client.post(
            f"{settings.ollama_base_url}/api/chat",
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]


async def _ollama_chat_stream(
    messages: list[dict[str, str]],
    *,
    max_tokens: int | None = None,
    timeout_seconds: float | None = None,
) -> AsyncIterator[str]:
    async with httpx.AsyncClient(
        timeout=timeout_seconds or settings.ollama_timeout_seconds
    ) as client:
        async with client.stream(
            "POST",
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.ollama_model,
                "messages": messages,
                "stream": True,
                "options": {
                    "num_predict": max_tokens or max(48, settings.ollama_num_predict),
                    "temperature": settings.ollama_temperature,
                },
            },
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                content = str((payload.get("message") or {}).get("content") or "")
                if content:
                    yield content
                if payload.get("done"):
                    break


def _validated_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    """Reject any call that bypasses the canonical prompt authority."""
    system_indexes = [
        index for index, message in enumerate(messages) if message.get("role") == "system"
    ]
    if system_indexes != [0]:
        raise ValueError("LLM messages require exactly one leading system prompt")
    if len(messages) < 2 or not str(messages[0].get("content") or "").strip():
        raise ValueError("LLM messages require a non-empty canonical prompt envelope")
    if CANONICAL_PROMPT_MARKER not in str(messages[0]["content"]):
        raise ValueError("LLM system message was not produced by the canonical prompt builder")
    return messages
