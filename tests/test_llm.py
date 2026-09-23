"""Tests for model resolution (making a pasted OpenRouter key just work)."""

from __future__ import annotations

import asyncio

import pytest

from backend.services import llm


@pytest.fixture(autouse=True)
def _no_env_model(monkeypatch):
    # isolate from a developer's CODEABC_MODEL override
    monkeypatch.delenv("CODEABC_MODEL", raising=False)


def test_default_without_key():
    assert llm._resolve_model() == "gpt-5-mini"


def test_litellm_drops_unsupported_params():
    # gpt-5 / o1 / o3 models reject a custom temperature; importing the llm
    # module must enable litellm.drop_params so those requests don't crash
    # (regression: a user hit UnsupportedParamsError on temperature=0.3 with the
    # default gpt-5-mini).
    import litellm

    assert litellm.drop_params is True


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


def test_is_error_text():
    assert llm.is_error_text("[LLM Error: AuthenticationError]")
    assert llm.is_error_text("  [LLM Error: boom]")  # tolerates leading space
    assert not llm.is_error_text('{"summary": "a real answer"}')
    assert not llm.is_error_text("")
    # the call helpers emit exactly this sentinel shape
    assert llm.is_error_text(f"{llm.LLM_ERROR_PREFIX} something]")


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content="ok"):
        self.choices = [_FakeChoice(content)]


@pytest.fixture
def capture_kwargs(monkeypatch):
    """Replace litellm.acompletion with a spy that records its kwargs."""
    captured: dict = {}

    async def fake_acompletion(**kwargs):
        captured.update(kwargs)
        return _FakeResponse()

    monkeypatch.setattr(llm.litellm, "acompletion", fake_acompletion)
    return captured


def test_call_llm_passes_api_base_and_model(capture_kwargs):
    # the wizard's chosen gateway + model must reach litellm verbatim
    result = asyncio.run(
        llm.call_llm(
            "hi",
            api_key="sk-sp-x",
            api_base="https://gw/v1",
            model="openai/qwen3.8-flash",
        )
    )
    assert result == "ok"
    assert capture_kwargs["api_base"] == "https://gw/v1"
    assert capture_kwargs["model"] == "openai/qwen3.8-flash"


def test_call_llm_uses_adaptive_max_tokens(capture_kwargs, monkeypatch):
    # regression: max_tokens was hard-coded to 4096, truncating long answers;
    # it now derives from the model's real output window via suggest_max_tokens.
    monkeypatch.setattr(llm, "suggest_max_tokens", lambda model: 12345)
    asyncio.run(llm.call_llm("hi", model="openai/x"))
    assert capture_kwargs["max_tokens"] == 12345


def test_call_llm_env_api_base_fallback(capture_kwargs, monkeypatch):
    monkeypatch.setenv("OPENAI_API_BASE", "https://env-gw/v1")
    asyncio.run(llm.call_llm("hi", model="openai/x"))
    assert capture_kwargs["api_base"] == "https://env-gw/v1"


def test_call_llm_no_api_base_when_unset(capture_kwargs, monkeypatch):
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    asyncio.run(llm.call_llm("hi", model="openai/x"))
    assert "api_base" not in capture_kwargs


def test_call_llm_redacts_key_from_error(monkeypatch):
    key = "sk-sp-SECRET123"

    async def boom(**kwargs):
        raise RuntimeError(f"auth failed for {key}")

    monkeypatch.setattr(llm.litellm, "acompletion", boom)
    result = asyncio.run(llm.call_llm("hi", api_key=key))
    assert llm.is_error_text(result)
    assert key not in result  # the credential never reaches a reader-visible string
    assert "***" in result


def test_llm_kwargs_reads_byok_headers():
    from backend.routers.analyze import _llm_kwargs

    class _Req:
        def __init__(self, headers):
            self.headers = headers

    headers = {
        "x-api-key": "k",
        "x-api-base": "https://gw/v1",
        "x-model": "openai/m",
        "x-api-protocol": "chat_completions",
    }
    assert _llm_kwargs(_Req(headers)) == {
        "api_key": "k",
        "api_base": "https://gw/v1",
        "model": "openai/m",
        "protocol": "chat_completions",
    }
    # absent headers -> all None, so llm falls back to its env/default path
    assert _llm_kwargs(_Req({})) == {
        "api_key": None,
        "api_base": None,
        "model": None,
        "protocol": None,
    }


def test_resolve_model_with_protocol():
    # the settings form's BYOK path qualifies a bare gateway model by protocol
    assert llm._resolve_model(model="qwen3.8-flash", protocol="chat_completions") == (
        "openai/qwen3.8-flash"
    )
    assert llm._resolve_model(model="claude-x", protocol="anthropic_messages") == (
        "anthropic/claude-x"
    )


def test_resolve_base_normalises_per_protocol():
    # OpenAI-style bases end in /v1; Anthropic-style are bare roots
    assert llm._resolve_base("https://gw", "chat_completions") == "https://gw/v1"
    assert llm._resolve_base("https://gw/v1", "anthropic_messages") == "https://gw"
