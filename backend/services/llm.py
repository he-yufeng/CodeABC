"""LLM integration via litellm — supports any model provider."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator

import litellm

logger = logging.getLogger(__name__)

# default model — can be overridden via env
_DEFAULT_MODEL = os.getenv("CODEABC_MODEL", "gpt-4o-mini")


def _get_model() -> str:
    return os.getenv("CODEABC_MODEL", _DEFAULT_MODEL)


async def stream_llm(
    prompt: str,
    *,
    api_key: str | None = None,
    model: str | None = None,
) -> AsyncGenerator[str, None]:
    """Stream LLM response chunks."""
    model = model or _get_model()

    kwargs: dict = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "temperature": 0.3,
        "max_tokens": 4096,
    }
    if api_key:
        kwargs["api_key"] = api_key

    try:
        response = await litellm.acompletion(**kwargs)
        async for chunk in response:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        yield f"[LLM Error: {e}]"


async def call_llm(
    prompt: str,
    *,
    api_key: str | None = None,
    model: str | None = None,
) -> str:
    """Non-streaming LLM call. Returns the full response text."""
    model = model or _get_model()

    kwargs: dict = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 4096,
    }
    if api_key:
        kwargs["api_key"] = api_key

    try:
        response = await litellm.acompletion(**kwargs)
        return response.choices[0].message.content or ""
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        return f"[LLM Error: {e}]"
