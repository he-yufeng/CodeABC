"""CI quality-gate map — the automated checks your code must pass on push / PR.

Entry points answer "how do I *start* this", CLI commands answer "what can I
*type*", and the scheduled-tasks map answers "what runs on a *timer*". This answers
the question a newcomer feels most sharply the first time they open a pull
request: **when I hand my change in, what does the project check automatically —
and what has to pass before it is allowed in?** A continuous-integration pipeline
quietly runs a row of gates (lint, formatting, type-checks, tests, a security
scan, a build) on every push, and one red cross usually blocks the merge. Seeing
the gates up front turns an intimidating wall of red into a short, known checklist.

It reads the CI configuration CodeABC already loaded — no LLM, nothing to run —
recognising the pipelines people reach for most:

  GitHub Actions   ``.github/workflows/*.yml``
  pre-commit       ``.pre-commit-config.yaml``
  GitLab CI        ``.gitlab-ci.yml``
  CircleCI         ``.circleci/config.yml``
  Azure Pipelines  ``azure-pipelines.yml``
  Travis CI        ``.travis.yml``
  Jenkins          ``Jenkinsfile``

Each gate is classified — by the tool that runs it — into a plain-language bucket
(代码规范 / 代码格式 / 类型检查 / 自动化测试 / 测试覆盖率 / 安全扫描 / 构建打包 /
部署发布) so a non-programmer can read the row without knowing what ``ruff`` or
``tsc`` are. For GitHub Actions it also glosses the trigger (``on: [push,
pull_request]`` → ``每次推送代码、每次 PR``).

:func:`find_ci_checks` is pure over the file contents, so it is unit-testable
with plain strings and needs no repository.

Limitations (kept honest on purpose):

  * Tool-signature based, not a pipeline parse. A gate run through an unusual
    wrapper, a hand-rolled shell script, or a composite action this module does
    not recognise will be missed; a tool name that only appears in a CI comment
    may be over-counted. Restricting the scan to known CI files keeps both rare.
  * Only the trigger of GitHub Actions workflows is glossed; the other systems
    express their run rules too many ways to read reliably, so their trigger is
    left blank rather than guessed at.
  * Cron-*scheduled* runs are deliberately left to the scheduled-tasks map so the
    two maps do not double-count; this one is about checks that gate a change.
"""

from __future__ import annotations

import re

_YAML_SUFFIXES = (".yml", ".yaml")

# Plain-language label for each gate category, in display order.
_CATEGORY_LABEL = {
    "lint": "代码规范检查",
    "format": "代码格式检查",
    "typecheck": "类型检查",
    "test": "自动化测试",
    "coverage": "测试覆盖率",
    "security": "安全扫描",
    "build": "构建打包",
    "deploy": "部署 / 发布",
}
_CATEGORY_ORDER = list(_CATEGORY_LABEL)

_SYSTEM_LABEL = {
    "github-actions": "GitHub Actions",
    "pre-commit": "pre-commit",
    "gitlab-ci": "GitLab CI",
    "circleci": "CircleCI",
    "azure-pipelines": "Azure Pipelines",
    "travis": "Travis CI",
    "jenkins": "Jenkins",
}

# (category, tool label, signature). Every signature is matched independently, so
# a single ``run:`` line that chains several tools is credited to each. The only
# ordering that matters is keeping ``ruff format`` distinguishable from a bare
# ``ruff`` lint pass, which the negative lookahead below handles regardless.
_SIGNATURES: list[tuple[str, str, str]] = [
    # --- lint --------------------------------------------------------------
    ("lint", "ruff", r"\bruff\b(?![-\s]format\b)"),
    ("lint", "flake8", r"\bflake8\b"),
    ("lint", "pylint", r"\bpylint\b"),
    ("lint", "eslint", r"\beslint\b"),
    ("lint", "golangci-lint", r"\bgolangci-lint\b"),
    ("lint", "clippy", r"\bclippy\b"),
    ("lint", "rubocop", r"\brubocop\b"),
    ("lint", "shellcheck", r"\bshellcheck\b"),
    ("lint", "stylelint", r"\bstylelint\b"),
    ("lint", "markdownlint", r"\bmarkdownlint\b"),
    # --- format ------------------------------------------------------------
    ("format", "ruff format", r"\bruff[-\s]format\b"),
    ("format", "black", r"\bblack\b"),
    ("format", "isort", r"\bisort\b"),
    ("format", "prettier", r"\bprettier\b"),
    ("format", "gofmt", r"\bgofmt\b|\bgo\s+fmt\b"),
    ("format", "rustfmt", r"\brustfmt\b|\bcargo\s+fmt\b"),
    ("format", "clang-format", r"\bclang-format\b"),
    # --- typecheck ---------------------------------------------------------
    ("typecheck", "mypy", r"\bmypy\b"),
    ("typecheck", "pyright", r"\bpyright\b"),
    ("typecheck", "tsc", r"\btsc\b"),
    ("typecheck", "pytype", r"\bpytype\b"),
    # --- test --------------------------------------------------------------
    ("test", "pytest", r"\bpytest\b"),
    ("test", "tox", r"\btox\b"),
    ("test", "nox", r"\bnox\b"),
    ("test", "unittest", r"\bunittest\b"),
    ("test", "jest", r"\bjest\b"),
    ("test", "vitest", r"\bvitest\b"),
    ("test", "mocha", r"\bmocha\b"),
    ("test", "npm test", r"\bnpm\s+(?:run\s+)?test\b"),
    ("test", "yarn test", r"\byarn\s+(?:run\s+)?test\b"),
    ("test", "pnpm test", r"\bpnpm\s+(?:run\s+)?test\b"),
    ("test", "go test", r"\bgo\s+test\b"),
    ("test", "cargo test", r"\bcargo\s+test\b"),
    ("test", "gradle test", r"\bgradle\s+test\b"),
    ("test", "mvn test", r"\bmvn\s+test\b"),
    ("test", "rspec", r"\brspec\b"),
    # --- coverage ----------------------------------------------------------
    ("coverage", "codecov", r"\bcodecov\b"),
    ("coverage", "coveralls", r"\bcoveralls\b"),
    ("coverage", "coverage", r"\bcoverage\s+(?:run|report|xml|html)\b"),
    ("coverage", "pytest --cov", r"--cov\b"),
    # --- security ----------------------------------------------------------
    ("security", "bandit", r"\bbandit\b"),
    ("security", "pip-audit", r"\bpip-audit\b"),
    ("security", "npm audit", r"\bnpm\s+audit\b"),
    ("security", "trivy", r"\btrivy\b"),
    ("security", "CodeQL", r"\bcodeql\b"),
    ("security", "semgrep", r"\bsemgrep\b"),
    ("security", "snyk", r"\bsnyk\b"),
    ("security", "gitleaks", r"\bgitleaks\b"),
    ("security", "safety", r"\bsafety\s+check\b"),
    # --- build -------------------------------------------------------------
    ("build", "docker build", r"\bdocker\s+build\b"),
    ("build", "npm run build", r"\bnpm\s+run\s+build\b"),
    ("build", "yarn build", r"\byarn\s+(?:run\s+)?build\b"),
    ("build", "pnpm build", r"\bpnpm\s+(?:run\s+)?build\b"),
    ("build", "go build", r"\bgo\s+build\b"),
    ("build", "cargo build", r"\bcargo\s+build\b"),
    ("build", "python -m build", r"\bpython\s+-m\s+build\b"),
    ("build", "poetry build", r"\bpoetry\s+build\b"),
    ("build", "mvn package", r"\bmvn\s+package\b"),
    ("build", "gradle build", r"\bgradle\s+build\b"),
    # --- deploy ------------------------------------------------------------
    ("deploy", "twine upload", r"\btwine\s+upload\b"),
    ("deploy", "npm publish", r"\bnpm\s+publish\b"),
    ("deploy", "docker push", r"\bdocker\s+push\b"),
    ("deploy", "gh release", r"\bgh\s+release\b"),
    ("deploy", "PyPI publish", r"pypa/gh-action-pypi-publish"),
    ("deploy", "GitHub Release", r"softprops/action-gh-release"),
]

_COMPILED = [(cat, tool, re.compile(pat, re.IGNORECASE)) for cat, tool, pat in _SIGNATURES]

# GitHub Actions ``on:`` events worth glossing, in display order. ``pull_request``
# and its ``_target`` variant collapse to one label, so the more specific name is
# listed first and the duplicate is dropped by the seen-set in :func:`_gh_trigger`.
_EVENT_LABELS = [
    ("push", "每次推送代码"),
    ("pull_request_target", "每次 PR"),
    ("pull_request", "每次 PR"),
    ("workflow_dispatch", "手动触发"),
    ("release", "发布时"),
    ("schedule", "定时触发"),
    ("workflow_call", "被其他流程调用"),
    ("merge_group", "合并队列"),
]


def _line_of(content: str, pos: int) -> int:
    return content.count("\n", 0, pos) + 1


def _ci_system(path: str) -> str | None:
    """Classify a path as a known CI config, or ``None`` if it is not one."""
    norm = "/" + path.replace("\\", "/").lstrip("/")
    base = norm.rsplit("/", 1)[-1]
    if "/.github/workflows/" in norm and base.endswith(_YAML_SUFFIXES):
        return "github-actions"
    if base == ".pre-commit-config.yaml":
        return "pre-commit"
    if base in (".gitlab-ci.yml", ".gitlab-ci.yaml"):
        return "gitlab-ci"
    if "/.circleci/" in norm and base.endswith(_YAML_SUFFIXES):
        return "circleci"
    if base in ("azure-pipelines.yml", "azure-pipelines.yaml"):
        return "azure-pipelines"
    if base in (".travis.yml", ".travis.yaml"):
        return "travis"
    if base == "Jenkinsfile":
        return "jenkins"
    return None


def _gh_trigger(content: str) -> str:
    """Plain-language gloss of a GitHub Actions ``on:`` trigger, else ``""``.

    Captures the ``on:`` value whether it is inline (``on: [push]`` / ``on: push``)
    or a nested block, then names the events it recognises.
    """
    m = re.search(
        r"^on:(?P<inline>[^\n]*)\n(?P<body>(?:[ \t]+[^\n]*\n?)*)",
        content,
        re.MULTILINE,
    )
    if m:
        scope = m.group("inline") + "\n" + m.group("body")
    else:
        inline = re.search(r"^on:(?P<inline>[^\n]*)$", content, re.MULTILINE)
        scope = inline.group("inline") if inline else ""
    if not scope.strip():
        return ""

    labels: list[str] = []
    seen: set[str] = set()
    for event, label in _EVENT_LABELS:
        if label in seen:
            continue
        if re.search(rf"\b{event}\b", scope):
            seen.add(label)
            labels.append(label)
    return "、".join(labels)


def find_ci_checks(file_contents: dict[str, str], *, limit: int = 60) -> dict:
    """Collect the automated quality gates a project runs in CI.

    Args:
        file_contents: mapping of path to file text (as CodeABC already read it).
        limit: how many checks to return in the sorted list.

    Returns ``{"total", "systems", "categories", "checks"}`` where each check is
    ``{"tool", "category", "system", "trigger", "path", "line"}``.
    """
    checks: list[dict] = []
    seen: set[tuple] = set()

    for path, content in file_contents.items():
        if not content:
            continue
        system = _ci_system(path)
        if system is None:
            continue
        trigger = _gh_trigger(content) if system == "github-actions" else ""
        for category, tool, rx in _COMPILED:
            match = rx.search(content)
            if not match:
                continue
            key = (path, category, tool)
            if key in seen:
                continue
            seen.add(key)
            checks.append(
                {
                    "tool": tool,
                    "category": category,
                    "system": system,
                    "trigger": trigger,
                    "path": path,
                    "line": _line_of(content, match.start()),
                }
            )

    order = {category: i for i, category in enumerate(_CATEGORY_ORDER)}
    checks.sort(key=lambda c: (c["path"], order.get(c["category"], 99), c["line"]))
    systems = sorted({c["system"] for c in checks})
    categories = [c for c in _CATEGORY_ORDER if any(ck["category"] == c for ck in checks)]
    return {
        "total": len(checks),
        "systems": systems,
        "categories": categories,
        "checks": checks[:limit],
    }


def render_ci_checks_markdown(project_name: str, data: dict | None) -> str:
    """Render the CI quality-gate map as Markdown, or ``""`` if none were found."""
    checks = (data or {}).get("checks") or []
    if not checks:
        return ""

    lines = [
        f"# {project_name} — 提交代码后会自动跑的检查（CI 质量门禁）",
        "",
        "> 你把改动交上去（push 或开 PR）之后，下面这些检查会自动跑一遍，"
        "可以把它们当成“机器人审稿”——任何一项亮红叉，改动通常就进不去。"
        "提前知道有哪几道关卡，红叉就不再吓人，照着改过去即可。"
        "（会自己定时跑的任务另见“定时任务”地图，这里只看挡在改动前的检查。）",
        "",
        "## 这个项目会自动检查",
    ]

    by_category: dict[str, list[str]] = {}
    for check in checks:
        tools = by_category.setdefault(check["category"], [])
        if check["tool"] not in tools:
            tools.append(check["tool"])
    for category in _CATEGORY_ORDER:
        if category in by_category:
            tools = "、".join(f"`{tool}`" for tool in by_category[category])
            lines.append(f"- **{_CATEGORY_LABEL[category]}**：{tools}")
    lines.append("")
    lines.append("## 按配置文件")

    current_path = None
    for check in checks:
        if check["path"] != current_path:
            current_path = check["path"]
            system_label = _SYSTEM_LABEL.get(check["system"], check["system"])
            head = f"### `{current_path}` · {system_label}"
            if check["trigger"]:
                head += f" — {check['trigger']}"
            lines.append(head)
        label = _CATEGORY_LABEL[check["category"]]
        lines.append(f"- {label}：`{check['tool']}`  第 {check['line']} 行")
    return "\n".join(lines).rstrip() + "\n"
