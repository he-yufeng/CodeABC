"""Language-specific annotation guidance and its route-level cache contract."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.prompts.annotate import build_annotation_prompt
from backend.services import cache


@pytest.mark.parametrize(
    ("alias", "expected"),
    [("jsx", "Promise"), ("tsx", "interface"), ("golang", "goroutine")],
)
def test_language_aliases_keep_the_source_fence_and_add_guidance(alias, expected):
    prompt = build_annotation_prompt("answer = 42\n", alias)

    assert expected in prompt
    assert f"```{alias}" in prompt


def test_unknown_language_keeps_the_generic_prompt():
    prompt = build_annotation_prompt("answer = 42\n", "python")

    assert "额外解释要求" not in prompt
    assert "answer = 42" in prompt


def test_annotation_route_separates_language_profiles_and_caches_each(monkeypatch):
    content = "answer = 42\n"
    cases = [
        ("src/main.js", "javascript", ("Promise", "async/await")),
        ("src/main.ts", "typescript", ("interface", "import type")),
        ("src/main.go", "go", ("goroutine", "err != nil")),
    ]
    project = {
        "files": [
            {"path": path, "size": len(content), "language": language}
            for path, language, _ in cases
        ],
        "file_contents": {path: content for path, _, _ in cases},
    }
    calls = []
    stored = {}

    async def fake_get_project(project_id):
        return project if project_id == "demo" else None

    async def fake_call_llm(prompt, *, api_key=None):
        calls.append(prompt)
        return '[{"line_start": 1, "line_end": 1, "annotation": "给答案赋值"}]'

    async def fake_get(key):
        return stored.get(key)

    async def fake_put(key, value):
        stored[key] = value

    async def no_rate_limit(request):
        return None

    monkeypatch.setattr("backend.routers.analyze.get_project_data", fake_get_project)
    monkeypatch.setattr("backend.routers.analyze.call_llm", fake_call_llm)
    monkeypatch.setattr("backend.routers.analyze._enforce_rate_limit", no_rate_limit)
    monkeypatch.setattr(cache, "get", fake_get)
    monkeypatch.setattr(cache, "put", fake_put)

    client = TestClient(app)
    for path, language, _ in cases:
        url = f"/api/project/demo/file/{path}/annotations"
        first = client.get(url)
        second = client.get(url)

        assert first.status_code == 200 and second.status_code == 200
        assert first.json()["language"] == language
        assert first.json()["annotations"] == [
            {"line_start": 1, "line_end": 1, "annotation": "给答案赋值"}
        ]
        assert second.json() == first.json()

    assert len(stored) == len(cases)
    assert len(calls) == len(cases)
    for (_, language, markers), prompt in zip(cases, calls, strict=True):
        assert f" {language} " in prompt
        for marker in markers:
            assert marker in prompt
