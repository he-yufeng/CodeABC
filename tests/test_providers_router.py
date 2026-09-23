"""Tests for the protocol check + live model discovery endpoints."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.routers import providers as router_module

_KEY = "sk-sp-SECRET123"


def _client() -> TestClient:
    # Deliberately not used as a context manager: that would fire the app's
    # lifespan (init_db) and write a real cache DB; these routes never touch it.
    return TestClient(app)


class _FakeResp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=self)


class _FakeAsyncClient:
    last_url = ""
    last_headers: dict = {}
    post_resp = None

    def __init__(self, resp):
        self._resp = resp

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, headers=None):
        _FakeAsyncClient.last_url = url
        _FakeAsyncClient.last_headers = headers or {}
        return self._resp

    async def post(self, url, json=None, headers=None):
        _FakeAsyncClient.last_url = url
        _FakeAsyncClient.last_headers = headers or {}
        return _FakeAsyncClient.post_resp or _FakeResp(200, {"id": "ping"})


@pytest.fixture
def patch_httpx(monkeypatch):
    def _install(resp):
        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(resp))
        _FakeAsyncClient.last_url = ""
        _FakeAsyncClient.last_headers = {}
        _FakeAsyncClient.post_resp = None
    return _install


def test_protocols_endpoint_lists_protocols():
    r = _client().get("/api/protocols")
    assert r.status_code == 200
    protos = r.json()["protocols"]
    assert [p["id"] for p in protos] == ["chat_completions", "anthropic_messages"]
    # registry data only — no secrets leak into the listing
    assert all("api_key" not in p for p in protos)
    assert protos[0]["base_hint"]
    # both languages ship in the listing so the form can render either
    assert all(p["label_zh"] and p["wire_zh"] for p in protos)


def test_check_requires_base_url():
    r = _client().post(
        "/api/protocols/check", json={"protocol": "chat_completions", "api_key": _KEY}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "Base URL" in (body["diagnosis"] or "")


def test_check_unknown_protocol():
    r = _client().post(
        "/api/protocols/check", json={"protocol": "nope", "api_base": "https://gw"}
    )
    assert r.json()["ok"] is False


def test_check_pings_selected_model_chat(patch_httpx):
    patch_httpx(_FakeResp(200, {"data": []}))
    r = _client().post(
        "/api/protocols/check",
        json={
            "protocol": "chat_completions",
            "api_base": "https://gw.example.com",
            "api_key": _KEY,
            "model": "qwen3.8-flash",
        },
    )
    body = r.json()
    assert body["ok"] is True
    # base normalised to the OpenAI-style /v1 convention
    assert body["base_url"] == "https://gw.example.com/v1"
    # only the selected model is tested, via a 1-token chat completion
    assert _FakeAsyncClient.last_url == "https://gw.example.com/v1/chat/completions"
    # bearer auth for the OpenAI-style protocol
    assert _FakeAsyncClient.last_headers.get("Authorization") == f"Bearer {_KEY}"
    # the raw key never appears in the response body
    assert body["masked_key"] == "sk-sp-***T123"
    assert _KEY not in r.text


def test_check_anthropic_pings_messages(patch_httpx):
    patch_httpx(_FakeResp(200, {"data": []}))
    r = _client().post(
        "/api/protocols/check",
        json={
            "protocol": "anthropic_messages",
            "api_base": "https://api.anthropic.com/v1",
            "api_key": "sk-ant-SECRET1",
            "model": "claude-x",
        },
    )
    body = r.json()
    assert body["ok"] is True
    # Anthropic-style base is a bare root (client appends /v1/messages)
    assert body["base_url"] == "https://api.anthropic.com"
    assert _FakeAsyncClient.last_url == "https://api.anthropic.com/v1/messages"
    assert _FakeAsyncClient.last_headers.get("x-api-key") == "sk-ant-SECRET1"


def test_check_unauthorized_diagnosis(patch_httpx):
    patch_httpx(_FakeResp(200, {"data": []}))
    _FakeAsyncClient.post_resp = _FakeResp(401, {})
    r = _client().post(
        "/api/protocols/check",
        json={
            "protocol": "chat_completions",
            "api_base": "https://gw/v1",
            "api_key": _KEY,
            "model": "m",
        },
    )
    body = r.json()
    assert body["ok"] is False
    assert body["status_code"] == 401
    assert "key" in (body["diagnosis"] or "").lower()
    # the same diagnosis is available in Chinese for the zh UI
    assert body["diagnosis_zh"] and body["diagnosis_zh"] != body["diagnosis"]


def test_check_requires_model():
    # the check tests exactly one model, so it refuses to run without one
    r = _client().post(
        "/api/protocols/check",
        json={"protocol": "chat_completions", "api_base": "https://gw/v1", "api_key": _KEY},
    )
    body = r.json()
    assert body["ok"] is False
    assert "model" in (body["diagnosis"] or "").lower()
    assert body["diagnosis_zh"]


def test_models_endpoint_discovers_with_prefix(patch_httpx, monkeypatch):
    monkeypatch.setattr(
        router_module,
        "model_metadata",
        lambda m: {"mode": None, "max_input_tokens": 100, "max_output_tokens": 50,
                   "input_cost_per_token": None, "output_cost_per_token": None,
                   "metadata_source": "test"},
    )
    patch_httpx(_FakeResp(200, {"data": [{"id": "qwen3.8-flash"}, {"id": "wan2.7-image"}]}))
    r = _client().get(
        "/api/models",
        params={"protocol": "chat_completions", "api_base": "https://gw/v1"},
        headers={"x-api-key": _KEY},
    )
    body = r.json()
    assert body["count"] == 2
    chat = body["models"][0]
    assert chat["id"] == "qwen3.8-flash"
    assert chat["litellm_model"] == "openai/qwen3.8-flash"
    assert chat["chat"] is True
    img = body["models"][1]
    assert img["chat"] is False  # name hints a non-chat model
    # the picker shows the reason inline, so it needs both languages too
    assert chat["chat_reason_zh"] and img["chat_reason_zh"]


def test_models_endpoint_requires_protocol_and_base():
    r = _client().get("/api/models")
    body = r.json()
    assert body["models"] == []
    assert body["error"]


def test_models_endpoint_redacts_key_from_transport_error(monkeypatch):
    class _Boom:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, headers=None):
            raise httpx.ConnectError(f"proxy denied for {_KEY}")

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _Boom())
    r = _client().get(
        "/api/models",
        params={"protocol": "chat_completions", "api_base": "https://gw/v1"},
        headers={"x-api-key": _KEY},
    )
    body = r.json()
    assert body["models"] == []
    assert _KEY not in body["error"]
