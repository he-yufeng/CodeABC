"""Tests for GitHub URL parsing — the many shapes a non-technical user pastes."""

from __future__ import annotations

import pytest

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
