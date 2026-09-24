"""Tests for the wire-protocol registry and model-capability helpers."""

from __future__ import annotations

import pytest

from backend.services import providers


class _FakeLitellm:
    """Stand-in for litellm: a model->info catalog, raising for unknown ids."""

    def __init__(self, catalog):
        self.model_cost = catalog

    def get_model_info(self, model):
        if model in self.model_cost:
            return self.model_cost[model]
        raise KeyError(model)


@pytest.fixture
def fake_catalog(monkeypatch):
    def _install(catalog):
        monkeypatch.setattr(providers, "_load_litellm", lambda: _FakeLitellm(catalog))

    return _install


def test_protocols_are_well_formed():
    protos = providers.list_protocols()
    assert [p.id for p in protos] == ["chat_completions", "anthropic_messages"]
    for p in protos:
        assert p.label and p.wire and p.litellm_prefix and p.models_path and p.base_hint
        # the settings form is bilingual, so every label carries both languages
        assert p.label_zh and p.wire_zh
        assert p.label_zh != p.label
    chat = providers.get_protocol("chat_completions")
    assert chat.base_has_v1 is True
    assert chat.auth_header == "authorization"
    assert chat.models_path == "/models"
    anth = providers.get_protocol("anthropic_messages")
    assert anth.base_has_v1 is False
    assert anth.auth_header == "x-api-key"
    assert anth.models_path == "/v1/models"


def test_get_protocol_unknown():
    assert providers.get_protocol("nope") is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://gw", "https://gw/v1"),
        ("https://gw/", "https://gw/v1"),
        ("https://gw/v1", "https://gw/v1"),
        ("https://gw/v1/", "https://gw/v1"),
        ("https://gw/compatible-mode/v1", "https://gw/compatible-mode/v1"),
    ],
)
def test_normalize_base_chat_completions(raw, expected):
    assert providers.normalize_base_url(raw, "chat_completions") == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://api.anthropic.com", "https://api.anthropic.com"),
        ("https://api.anthropic.com/v1", "https://api.anthropic.com"),
        ("https://api.anthropic.com/v1/", "https://api.anthropic.com"),
    ],
)
def test_normalize_base_anthropic(raw, expected):
    assert providers.normalize_base_url(raw, "anthropic_messages") == expected


def test_normalize_base_unknown_protocol_passthrough():
    assert providers.normalize_base_url("https://gw/v1/", "nope") == "https://gw/v1"


def test_resolve_litellm_model():
    resolve = providers.resolve_litellm_model
    assert resolve("chat_completions", "qwen3.8-flash") == "openai/qwen3.8-flash"
    assert resolve("chat_completions", "openai/qwen3.8-flash") == "openai/qwen3.8-flash"
    assert resolve("anthropic_messages", "claude-x") == "anthropic/claude-x"


def test_resolve_litellm_model_errors():
    with pytest.raises(ValueError):
        providers.resolve_litellm_model("nope", "m")
    with pytest.raises(ValueError):
        providers.resolve_litellm_model("chat_completions", "")


def test_mask_key():
    assert providers.mask_key("sk-sp-SECRET123") == "sk-sp-***T123"
    assert providers.mask_key("short") == "***"
    assert providers.mask_key("") == ""


def test_redact_secret():
    assert providers.redact_secret("auth failed sk-ABC", "sk-ABC") == "auth failed ***"
    assert providers.redact_secret("no secret", "") == "no secret"


def test_suggest_max_tokens_direct_hit(fake_catalog):
    fake_catalog({"openai/qwen3.8-flash": {"max_output_tokens": 131072}})
    # huge output window is capped so cost stays bounded
    assert providers.suggest_max_tokens("openai/qwen3.8-flash") == 32768


def test_suggest_max_tokens_cross_prefix(fake_catalog):
    # gateway reuses a model name litellm only knows under another prefix
    fake_catalog({"openrouter/qwen/qwen3.8-flash": {"max_output_tokens": 32768}})
    assert providers.suggest_max_tokens("openai/qwen3.8-flash") == 32768


def test_suggest_max_tokens_unknown(fake_catalog):
    fake_catalog({})
    assert providers.suggest_max_tokens("openai/mystery") == 8192


def test_suggest_max_tokens_floor(fake_catalog):
    fake_catalog({"openai/tiny": {"max_output_tokens": 10}})
    assert providers.suggest_max_tokens("openai/tiny") == 4096


def test_model_metadata_cross_prefix(fake_catalog):
    fake_catalog({"openrouter/qwen/qwen3.8-flash": {"max_input_tokens": 1_000_000}})
    meta = providers.model_metadata("openai/qwen3.8-flash")
    assert meta["max_input_tokens"] == 1_000_000
    assert meta["metadata_source"] == "cross_prefix"


def test_model_metadata_unknown(fake_catalog):
    fake_catalog({})
    meta = providers.model_metadata("openai/mystery")
    assert meta["max_input_tokens"] is None
    assert meta["metadata_source"] == "unknown"


def test_model_metadata_matches_a_nested_bare_name(fake_catalog):
    # the suffix index must still find a name litellm knows two segments deep
    fake_catalog({"openrouter/qwen/qwen3.8-flash": {"max_output_tokens": 32768}})
    meta = providers.model_metadata("openai/qwen/qwen3.8-flash")
    assert meta["metadata_source"] == "cross_prefix"
    assert meta["max_output_tokens"] == 32768


def test_model_metadata_never_matches_a_partial_name(fake_catalog):
    # "flash" is a segment of the catalog key but not a whole bare name
    fake_catalog({"openrouter/qwen/qwen3.8-flash": {"max_output_tokens": 32768}})
    assert providers.model_metadata("openai/flash")["metadata_source"] == "unknown"
