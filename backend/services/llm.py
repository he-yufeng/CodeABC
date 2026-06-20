"""LLM integration via litellm — supports any model provider."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator

import litellm

logger = logging.getLogger(__name__)

# Default model for a direct-provider key (OpenAI etc.). gpt-5-mini is the
# current cheap OpenAI default; override with CODEABC_MODEL for anything else.
_DEFAULT_MODEL = "gpt-5-mini"
# Default when the user pastes an OpenRouter key (sk-or-...). DeepSeek V4 Flash
# suits a beginner code-reader well: very cheap (~$0.09/$0.18 per Mtok), a 1M
# context to ingest whole files, reliable JSON output, and strong Chinese
# explanations — all checked live on OpenRouter (2026-06). Other verified picks,
# via CODEABC_MODEL: openrouter/anthropic/claude-haiku-4.5 (best explanations,
# ~10x pricier) or openrouter/google/gemini-3-flash-preview (1M context, strong
# at code). Note: openai/gpt-5-mini is not reliably reachable through OpenRouter.
_DEFAULT_OPENROUTER_MODEL = "openrouter/deepseek/deepseek-v4-flash"


def _resolve_model(api_key: str | None = None, model: str | None = None) -> str:
    """Pick the litellm model string, making a pasted OpenRouter key just work.

    An explicit model (the ``model`` argument or the ``CODEABC_MODEL`` env var)
    always wins. Otherwise the key's shape decides the provider: an OpenRouter
    key (``sk-or-...``) routes through OpenRouter, so a non-technical user only
    has to paste their key — there is no provider or ``openrouter/`` prefix to
    remember. Anything else falls back to the OpenAI default.
    """
    override = model or os.getenv("CODEABC_MODEL")
    is_openrouter_key = bool(api_key) and api_key.startswith("sk-or-")
    if override:
        # a bare model name alongside an OpenRouter key -> route it accordingly
        if is_openrouter_key and "/" not in override:
            return f"openrouter/{override}"
        return override
    return _DEFAULT_OPENROUTER_MODEL if is_openrouter_key else _DEFAULT_MODEL


async def stream_llm(
    prompt: str,
    *,
    api_key: str | None = None,
    model: str | None = None,
) -> AsyncGenerator[str, None]:
    """Stream LLM response chunks."""
    model = _resolve_model(api_key, model)

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
    model = _resolve_model(api_key, model)

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
