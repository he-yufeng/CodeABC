"""Tests for the contribution-map analyzer.

Plain-string inputs, no repository and no LLM — the same shape as
``test_release_map.py``. Each test pins one signal so a regression points at the
exact detector that broke.
"""

from __future__ import annotations

from backend.services.contributing import (
    find_contribution_guide,
    render_contributing_markdown,
)


def _kinds(data: dict) -> list[str]:
    return [r["kind"] for r in data["requirements"]]


def test_empty_project_has_nothing():
    data = find_contribution_guide({})
    assert data["has_guide"] is False
    assert data["requirements"] == []
    assert data["notes"] == []
    assert render_contributing_markdown("x", data) == ""


def test_contributing_file_is_the_guide():
    data = find_contribution_guide({"CONTRIBUTING.md": "How to help out.\n"})
    assert data["has_guide"] is True
    assert _kinds(data) == ["guide"]
    req = data["requirements"][0]
    assert req["label_zh"] == "贡献指南"
    assert req["path"] == "CONTRIBUTING.md"
    assert req["line"] == 0


def test_contributing_in_dot_github_counts():
    data = find_contribution_guide({".github/CONTRIBUTING.md": "x"})
    assert data["has_guide"] is True
    assert _kinds(data) == ["guide"]


def test_contributing_deep_in_examples_does_not_count():
    # A CONTRIBUTING.md buried in a sample project is not the repo's own guide.
    data = find_contribution_guide({"examples/widget/CONTRIBUTING.md": "x"})
    assert data["has_guide"] is False
    assert data["requirements"] == []


def test_dco_only_trusted_in_signal_files():
    # The same "Signed-off-by" string: trusted in CONTRIBUTING, ignored in source.
    in_guide = find_contribution_guide(
        {"CONTRIBUTING.md": "Every commit needs a Signed-off-by line (git commit -s)."}
    )
    assert "dco" in _kinds(in_guide)
    dco = next(r for r in in_guide["requirements"] if r["kind"] == "dco")
    assert dco["line"] == 1

    in_source = find_contribution_guide(
        {"src/app.py": "# Signed-off-by: someone in a code comment\n"}
    )
    assert "dco" not in _kinds(in_source)


def test_dco_app_config_file_counts():
    data = find_contribution_guide({".github/dco.yml": "require: true\n"})
    assert _kinds(data) == ["dco"]


def test_cla_detected_from_workflow():
    data = find_contribution_guide(
        {".github/workflows/cla.yml": "uses: contributor-assistant/github-action@v2\n"}
    )
    assert "cla" in _kinds(data)


def test_commit_convention_from_config_file():
    data = find_contribution_guide({"commitlint.config.js": "module.exports = {}\n"})
    assert _kinds(data) == ["commit-convention"]
    assert data["requirements"][0]["line"] == 0


def test_commit_convention_from_prose():
    data = find_contribution_guide(
        {"CONTRIBUTING.md": "Please follow Conventional Commits for your messages."}
    )
    assert "commit-convention" in _kinds(data)


def test_codeowners_and_templates_and_security():
    data = find_contribution_guide(
        {
            ".github/CODEOWNERS": "* @maintainer\n",
            ".github/PULL_REQUEST_TEMPLATE.md": "## What\n",
            ".github/ISSUE_TEMPLATE/bug.yml": "name: Bug\n",
            "SECURITY.md": "Email security@example.com\n",
            "CODE_OF_CONDUCT.md": "Be kind.\n",
        }
    )
    kinds = set(_kinds(data))
    assert {"codeowners", "pr-template", "issue-template", "security", "code-of-conduct"} <= kinds


def test_requirements_follow_display_order():
    # Provided out of order; output must follow the canonical _ORDER.
    data = find_contribution_guide(
        {
            "SECURITY.md": "x",
            ".github/dco.yml": "require: true",
            "CONTRIBUTING.md": "x",
        }
    )
    assert _kinds(data) == ["guide", "dco", "security"]


def test_shallowest_path_wins_on_duplicate():
    data = find_contribution_guide(
        {
            "docs/CONTRIBUTING.md": "deep one",
            "CONTRIBUTING.md": "root one",
        }
    )
    guide = next(r for r in data["requirements"] if r["kind"] == "guide")
    assert guide["path"] == "CONTRIBUTING.md"


def test_notes_warn_when_guide_missing_but_signals_present():
    data = find_contribution_guide({".github/dco.yml": "require: true"})
    assert any("CONTRIBUTING" in n for n in data["notes"])


def test_render_lists_requirements_and_notes():
    data = find_contribution_guide(
        {
            "CONTRIBUTING.md": "Use Conventional Commits and a Signed-off-by line.",
            ".github/CODEOWNERS": "* @maintainer",
        }
    )
    md = render_contributing_markdown("DemoProject", data)
    assert md.startswith("# DemoProject — 怎么给这个项目贡献代码")
    assert "贡献指南" in md
    assert "提交信息规范" in md
    assert "DCO 签署" in md
    assert "代码负责人" in md
    assert "## 一句话提醒" in md
    assert md.endswith("\n")


def test_render_none_is_empty():
    assert render_contributing_markdown("x", None) == ""
