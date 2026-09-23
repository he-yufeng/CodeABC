"""LLM integration via litellm — supports any model provider."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator

import litellm

from backend.services.providers import (
    normalize_base_url,
    redact_secret,
    resolve_litellm_model,
    suggest_max_tokens,
)

# Some models reject a custom temperature: gpt-5 / gpt-5-mini / gpt-5-codex and
# the o1 / o3 reasoning families only accept the default (temperature=1) and
# error on `temperature=0.3`. Since gpt-5-mini is our default OpenAI model, let
# litellm silently drop any param a given model doesn't support instead of
# crashing the request — models that do support temperature still honor it.
litellm.drop_params = True

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


def _resolve_model(
    api_key: str | None = None,
    model: str | None = None,
    protocol: str | None = None,
) -> str:
    """Pick the litellm model string for a request.

    With an explicit ``protocol`` (the settings form's BYOK path) the model is
    a bare gateway id qualified by that protocol's litellm prefix. Without one
    the legacy key-shape routing applies: an explicit model (argument or
    ``CODEABC_MODEL``) wins, else an OpenRouter key (``sk-or-...``) routes
    through OpenRouter, else the OpenAI default.
    """
    override = model or os.getenv("CODEABC_MODEL")
    if protocol:
        return resolve_litellm_model(protocol, override or _DEFAULT_MODEL)
    is_openrouter_key = bool(api_key) and api_key.startswith("sk-or-")
    if override:
        # a bare model name alongside an OpenRouter key -> route it accordingly
        if is_openrouter_key and "/" not in override:
            return f"openrouter/{override}"
        return override
    return _DEFAULT_OPENROUTER_MODEL if is_openrouter_key else _DEFAULT_MODEL


def _resolve_base(api_base: str | None, protocol: str | None) -> str | None:
    """Pick the gateway base URL, normalised to the protocol's convention."""
    base = api_base or os.getenv("OPENAI_API_BASE")
    if protocol and base:
        return normalize_base_url(base, protocol)
    return base


# On failure the call helpers below surface this sentinel instead of raising, so
# the streaming generator can finish cleanly. Routers detect it (is_error_text)
# and turn it into a proper error the UI can show in plain language, rather than
# letting a raw "[LLM Error: ...]" string reach the reader.
LLM_ERROR_PREFIX = "[LLM Error:"


def is_error_text(text: str) -> bool:
    """True if ``text`` is an LLM failure sentinel rather than real output."""
    return text.lstrip().startswith(LLM_ERROR_PREFIX)


async def stream_llm(
    prompt: str,
    *,
    api_key: str | None = None,
    model: str | None = None,
    api_base: str | None = None,
    protocol: str | None = None,
) -> AsyncGenerator[str, None]:
    """Stream LLM response chunks."""
    model = _resolve_model(api_key, model, protocol)

    kwargs: dict = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "temperature": 0.3,
        "max_tokens": suggest_max_tokens(model),
    }
    if api_key:
        kwargs["api_key"] = api_key
    base = _resolve_base(api_base, protocol)
    if base:
        kwargs["api_base"] = base

    try:
        response = await litellm.acompletion(**kwargs)
        async for chunk in response:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content
    except Exception as e:
        # the key can appear inside a provider's error text, so scrub it from
        # both the log line and the string the reader sees
        detail = redact_secret(str(e), api_key or "")
        logger.error(f"LLM call failed: {detail}")
        yield f"{LLM_ERROR_PREFIX} {detail}]"


async def call_llm(
    prompt: str,
    *,
    api_key: str | None = None,
    model: str | None = None,
    api_base: str | None = None,
    protocol: str | None = None,
) -> str:
    """Non-streaming LLM call. Returns the full response text."""
    model = _resolve_model(api_key, model, protocol)

    kwargs: dict = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": suggest_max_tokens(model),
    }
    if api_key:
        kwargs["api_key"] = api_key
    base = _resolve_base(api_base, protocol)
    if base:
        kwargs["api_base"] = base

    try:
        response = await litellm.acompletion(**kwargs)
        return response.choices[0].message.content or ""
    except Exception as e:
        detail = redact_secret(str(e), api_key or "")
        logger.error(f"LLM call failed: {detail}")
        return f"{LLM_ERROR_PREFIX} {detail}]"
