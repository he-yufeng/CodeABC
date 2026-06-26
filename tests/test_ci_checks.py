"""Tests for the CI quality-gate map."""

from backend.services.ci_checks import find_ci_checks, render_ci_checks_markdown


def _by_category(checks: list[dict]) -> dict[str, str]:
    return {c["category"]: c["tool"] for c in checks}


def test_github_actions_multi_tool_and_trigger():
    yaml = """
name: ci
on:
  push:
    branches: [main]
  pull_request:
jobs:
  test:
    steps:
      - run: ruff check .
      - run: ruff format --check .
      - run: mypy backend
      - run: pytest --cov=backend
"""
    result = find_ci_checks({".github/workflows/ci.yml": yaml})
    assert result["systems"] == ["github-actions"]
    # categories come back in the fixed display order, not match order
    assert result["categories"] == ["lint", "format", "typecheck", "test", "coverage"]
    cats = _by_category(result["checks"])
    assert cats["lint"] == "ruff"
    assert cats["format"] == "ruff format"
    assert cats["typecheck"] == "mypy"
    assert cats["test"] == "pytest"
    assert cats["coverage"] == "pytest --cov"
    # every check carries the workflow's trigger gloss
    assert all(c["trigger"] == "每次推送代码、每次 PR" for c in result["checks"])


def test_ruff_lint_and_format_are_separated():
    yaml = """
on: [push]
jobs:
  lint:
    steps:
      - run: ruff check
      - run: ruff format --check
"""
    result = find_ci_checks({".github/workflows/lint.yml": yaml})
    cats = _by_category(result["checks"])
    assert cats == {"lint": "ruff", "format": "ruff format"}
    # the lint pass is reported on its own line, not the format one
    lint = next(c for c in result["checks"] if c["category"] == "lint")
    format_ = next(c for c in result["checks"] if c["category"] == "format")
    assert lint["line"] < format_["line"]


def test_pre_commit_config_hooks():
    yaml = """
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    hooks:
      - id: ruff
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    hooks:
      - id: mypy
"""
    result = find_ci_checks({".pre-commit-config.yaml": yaml})
    assert result["systems"] == ["pre-commit"]
    cats = _by_category(result["checks"])
    assert cats["lint"] == "ruff"
    assert cats["format"] == "ruff format"
    assert cats["typecheck"] == "mypy"
    # non-GitHub-Actions systems leave the trigger blank rather than guess
    assert all(c["trigger"] == "" for c in result["checks"])


def test_non_github_systems_detected_with_blank_trigger():
    files = {
        ".gitlab-ci.yml": "test:\n  script:\n    - pytest\n    - flake8 .\n",
        "Jenkinsfile": "stage('Test') { steps { sh 'mvn test' } }\n",
        ".travis.yml": "script:\n  - npm test\n",
    }
    result = find_ci_checks(files)
    assert result["systems"] == ["gitlab-ci", "jenkins", "travis"]
    systems = {c["system"] for c in result["checks"]}
    assert systems == {"gitlab-ci", "jenkins", "travis"}
    tools = {c["tool"] for c in result["checks"]}
    assert {"pytest", "flake8", "mvn test", "npm test"} <= tools
    assert all(c["trigger"] == "" for c in result["checks"])


def test_security_build_and_deploy_buckets():
    yaml = """
on: [push]
jobs:
  release:
    steps:
      - run: bandit -r backend
      - run: docker build -t app .
      - run: twine upload dist/*
"""
    cats = _by_category(find_ci_checks({".github/workflows/release.yml": yaml})["checks"])
    assert cats["security"] == "bandit"
    assert cats["build"] == "docker build"
    assert cats["deploy"] == "twine upload"


def test_trigger_gloss_inline_and_dispatch_release():
    inline_yaml = "on: [push, pull_request]\njobs:\n  t:\n    steps:\n      - run: pytest\n"
    inline = find_ci_checks({".github/workflows/a.yml": inline_yaml})
    assert inline["checks"][0]["trigger"] == "每次推送代码、每次 PR"

    block_yaml = (
        "on:\n  workflow_dispatch:\n  release:\n    types: [published]\n"
        "jobs:\n  t:\n    steps:\n      - run: pytest\n"
    )
    block = find_ci_checks({".github/workflows/b.yml": block_yaml})
    assert block["checks"][0]["trigger"] == "手动触发、发布时"


def test_non_ci_files_are_ignored():
    files = {
        "src/app.py": "import pytest\n\ndef test_it():\n    assert True\n",
        "README.md": "Run `pytest` and `ruff check` to verify.",
        "config.yml": "on:\n  push:\nsteps:\n  - run: pytest\n",  # yaml, but not a CI path
    }
    result = find_ci_checks(files)
    assert result["total"] == 0
    assert result["checks"] == []


def test_duplicate_tool_collapses_to_one_check():
    yaml = """
on: [push]
jobs:
  test:
    steps:
      - run: pytest tests/unit
      - run: pytest tests/integration
"""
    result = find_ci_checks({".github/workflows/ci.yml": yaml})
    pytest_checks = [c for c in result["checks"] if c["tool"] == "pytest"]
    assert len(pytest_checks) == 1


def test_limit_caps_list_but_total_counts_all():
    yaml = """
on: [push]
jobs:
  lint:
    steps:
      - run: ruff check
      - run: flake8 .
      - run: pylint backend
      - run: eslint .
"""
    result = find_ci_checks({".github/workflows/lint.yml": yaml}, limit=2)
    assert result["total"] == 4
    assert len(result["checks"]) == 2


def test_sorted_by_path_then_category_then_line():
    files = {
        "b.yml": ".gitlab-ci.yml is matched by name, not this",  # ignored
        ".github/workflows/a.yml": "on: [push]\nsteps:\n  - run: pytest\n  - run: ruff check\n",
        ".gitlab-ci.yml": "test:\n  script:\n    - mypy .\n",
    }
    result = find_ci_checks(files)
    ordered = [(c["path"], c["category"]) for c in result["checks"]]
    # within the workflow, lint (ruff) sorts before test (pytest) by category order
    assert ordered == [
        (".github/workflows/a.yml", "lint"),
        (".github/workflows/a.yml", "test"),
        (".gitlab-ci.yml", "typecheck"),
    ]


def test_markdown_render_empty_and_grouped():
    assert render_ci_checks_markdown("Proj", {"checks": []}) == ""
    assert render_ci_checks_markdown("Proj", None) == ""

    data = find_ci_checks(
        {".github/workflows/ci.yml": "on:\n  push:\njobs:\n  t:\n    steps:\n      - run: pytest\n"}
    )
    md = render_ci_checks_markdown("Proj", data)
    assert "# Proj — 提交代码后会自动跑的检查（CI 质量门禁）" in md
    assert "## 这个项目会自动检查" in md
    assert "- **自动化测试**：`pytest`" in md
    assert "### `.github/workflows/ci.yml` · GitHub Actions — 每次推送代码" in md
    assert "自动化测试：`pytest`" in md
