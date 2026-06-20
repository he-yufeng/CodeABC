"""Tests for model resolution (making a pasted OpenRouter key just work)."""

from __future__ import annotations

import pytest

from backend.services import llm


@pytest.fixture(autouse=True)
def _no_env_model(monkeypatch):
    # isolate from a developer's CODEABC_MODEL override
    monkeypatch.delenv("CODEABC_MODEL", raising=False)


def test_default_without_key():
    assert llm._resolve_model() == "gpt-5-mini"


def test_openrouter_key_auto_routes():
    # an sk-or- key with no model picks the OpenRouter default
    assert llm._resolve_model("sk-or-v1-abc") == "openrouter/deepseek/deepseek-v4-flash"


def test_plain_openai_key_keeps_default():
    assert llm._resolve_model("sk-proj-abc") == "gpt-5-mini"


def test_explicit_model_wins_over_key():
    assert llm._resolve_model("sk-or-v1-abc", "openrouter/anthropic/claude-3.5-sonnet") == (
        "openrouter/anthropic/claude-3.5-sonnet"
    )


def test_bare_model_with_openrouter_key_gets_prefixed():
    # user typed a bare model name but pasted an OpenRouter key -> route it there
    assert llm._resolve_model("sk-or-v1-abc", "gpt-4o") == "openrouter/gpt-4o"


def test_bare_model_with_plain_key_unchanged():
    assert llm._resolve_model("sk-abc", "gpt-4o") == "gpt-4o"


def test_env_override(monkeypatch):
    monkeypatch.setenv("CODEABC_MODEL", "deepseek/deepseek-chat")
    assert llm._resolve_model() == "deepseek/deepseek-chat"
    # an OpenRouter key still routes the bare env model through OpenRouter
    monkeypatch.setenv("CODEABC_MODEL", "mistral-7b")
    assert llm._resolve_model("sk-or-v1-abc") == "openrouter/mistral-7b"
