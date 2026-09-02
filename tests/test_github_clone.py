"""Tests for GitHub URL parsing — the many shapes a non-technical user pastes."""

from __future__ import annotations

import asyncio

import pytest

from backend.services import github_clone
from backend.services.github_clone import _parse_github_url


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/he-yufeng/CodeABC",
        "https://github.com/he-yufeng/CodeABC/",
        "https://github.com/he-yufeng/CodeABC.git",
        "http://github.com/he-yufeng/CodeABC",
        "github.com/he-yufeng/CodeABC",
        "www.github.com/he-yufeng/CodeABC",
        "https://www.github.com/he-yufeng/CodeABC",
        # links copied from inside the repo (branch / file / tab / anchor)
        "https://github.com/he-yufeng/CodeABC/tree/main",
        "https://github.com/he-yufeng/CodeABC/tree/main/backend/services",
        "https://github.com/he-yufeng/CodeABC/blob/main/run.py",
        "https://github.com/he-yufeng/CodeABC?tab=readme-ov-file",
        "https://github.com/he-yufeng/CodeABC#installation",
        "https://github.com/he-yufeng/CodeABC/?tab=stars",
        # ssh + bare shorthand
        "git@github.com:he-yufeng/CodeABC.git",
        "he-yufeng/CodeABC",
        "he-yufeng/CodeABC.git",
        "  he-yufeng/CodeABC  ",
    ],
)
def test_parse_extracts_owner_and_repo(url):
    assert _parse_github_url(url) == ("he-yufeng", "CodeABC")


@pytest.mark.parametrize(
    "url",
    [
        "https://gitlab.com/he-yufeng/CodeABC",
        "https://bitbucket.org/he-yufeng/CodeABC",
        "https://example.com/not/github",
        "just-some-text",
        "https://github.com/he-yufeng",  # owner only, no repo
        "",
        "   ",
    ],
)
def test_parse_rejects_non_github_or_incomplete(url):
    with pytest.raises(ValueError):
        _parse_github_url(url)


def test_clone_repo_reports_missing_git(monkeypatch, tmp_path):
    # Redirect the cache dir so we never reuse a real clone, then make spawning
    # git fail as it would on a machine without git installed.
    monkeypatch.setattr(github_clone.tempfile, "gettempdir", lambda: str(tmp_path))

    async def no_git(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(github_clone.asyncio, "create_subprocess_exec", no_git)

    with pytest.raises(ValueError, match="Git isn't installed"):
        asyncio.run(github_clone.clone_repo("https://github.com/he-yufeng/CodeABC"))


@pytest.mark.parametrize(
    "url",
    [
        "github.com/he-yufeng/CodeABC",  # no protocol, what people paste
        "he-yufeng/CodeABC",  # bare shorthand
        "https://github.com/he-yufeng/CodeABC/tree/main",  # inner page link
    ],
)
def test_github_request_accepts_common_shapes(url):
    # The request model used to regex-gate on https://github.com/... and 422
    # these before the tolerant parser ever saw them (#1).
    from backend.models import GitHubRequest

    req = GitHubRequest(url=url)
    assert _parse_github_url(req.url) == ("he-yufeng", "CodeABC")


def test_github_request_rejects_empty():
    from pydantic import ValidationError

    from backend.models import GitHubRequest

    with pytest.raises(ValidationError):
        GitHubRequest(url="")
