"""Contribution map — what a project asks of you before it will take your change.

Entry points say how to *start* a project and the CI map says what gets
*checked* automatically; this answers the part a first-time contributor worries
about most: **if I want to hand a change in, what does this project expect from
me — which file do I read first, what do I have to sign, how must my commits and
my pull request look?** Almost all of that lives in a handful of well-known
"community health" files, and missing one of them is the usual reason a first PR
bounces before anyone even reads the code.

It reads the files CodeABC already loaded — no LLM, nothing run — recognising the
signals people reach for most:

  贡献指南        CONTRIBUTING(.md/.rst) in the repo root, ``.github/`` or ``docs/``
  PR 模板         ``.github/PULL_REQUEST_TEMPLATE`` (a single file or a folder)
  Issue 模板      ``.github/ISSUE_TEMPLATE`` (a single file or a folder of forms)
  行为准则        CODE_OF_CONDUCT(.md)
  代码负责人      CODEOWNERS — who is auto-requested to review what you touched
  安全披露        SECURITY(.md) — how to report a vulnerability privately
  DCO 签署        a "Signed-off-by" / ``git commit -s`` / DCO requirement
  CLA 签署        a Contributor License Agreement / cla-assistant gate
  提交信息规范    Conventional Commits / commitlint / commitizen

Every signal is glossed in plain Chinese (DCO 签署 → 每个提交带一行 Signed-off-by)
so a newcomer can read the row without knowing what a "DCO" or a "Conventional
Commit" is.

:func:`find_contribution_guide` is pure over the file contents, so it is
unit-testable with plain strings and needs no repository.

Limitations (kept honest on purpose):

  * Signature based, not a policy parse. Rules documented only in prose (a wiki, a
    website, a buried README paragraph) this module cannot see. To keep the
    content scans (DCO / CLA / commit convention) from firing on a stray mention
    in source code, they are restricted to the files those rules actually live in
    — CONTRIBUTING, the PR / issue templates, CI workflows and the dedicated
    config files.
  * Presence, not enforcement. It reports that a CLA bot or a commit convention is
    *configured*, not whether the maintainers truly block a merge on it.
  * Community-health files only. Code-level concerns (secrets in the tree, the
    licences of dependencies, the version it ships) have their own maps and are
    not repeated here.
"""

from __future__ import annotations

import re

# Plain-Chinese label + one-line gloss for each signal, in display order. The
# order is roughly "read this first" → "shape your commits" → "who signs off".
_LABELS = {
    "guide": "贡献指南",
    "pr-template": "PR 模板",
    "issue-template": "Issue 模板",
    "commit-convention": "提交信息规范",
    "dco": "DCO 签署",
    "cla": "CLA 签署",
    "codeowners": "代码负责人",
    "code-of-conduct": "行为准则",
    "security": "安全披露",
}
_ORDER = list(_LABELS)

_DETAIL = {
    "guide": "动手改之前先读它——项目把“怎么参与、怎么提交、本地怎么跑”都写在这里。",
    "pr-template": "提 PR 时会自动带出一个模板，按它把改动说明、关联 issue、自测情况填好再提交。",
    "issue-template": "提 issue 有固定格式，照着选类型、填字段，维护者更容易接手。",
    "commit-convention": (
        "提交信息要按约定式提交（Conventional Commits）写，例如 `fix: ...`、`feat: ...`。"
    ),
    "dco": (
        "每个提交都要带一行 Signed-off-by（用 `git commit -s` 自动加），声明这段代码可以被合入。"
    ),
    "cla": "首次贡献要先签一份贡献者许可协议（CLA），通常有机器人在 PR 里引导你点一下。",
    "codeowners": "你改到的目录会自动请对应的“代码负责人”来审查，少了他们点头通常合不进去。",
    "code-of-conduct": "社区有一份行为准则，约定大家怎么友好地协作、出问题找谁。",
    "security": "发现安全漏洞别公开提 issue，按这份说明走私下披露渠道。",
}

# Where GitHub looks for community-health files: the repo root, ``.github/`` or
# ``docs/`` (``.gitlab/`` for GitLab projects). A file only counts as, say, a
# CODEOWNERS if it sits in one of these — not anywhere a ``CONTRIBUTING.md``
# happens to appear deep inside an example folder.
_HEALTH_DIRS = ("/", "/.github/", "/docs/", "/.gitlab/")

# commitlint / commitizen config file names — strong evidence of a commit
# convention even with no prose to read.
_COMMIT_CONFIG = frozenset(
    {
        "commitlint.config.js",
        "commitlint.config.cjs",
        "commitlint.config.mjs",
        "commitlint.config.ts",
        ".commitlintrc",
        ".commitlintrc.js",
        ".commitlintrc.cjs",
        ".commitlintrc.json",
        ".commitlintrc.yml",
        ".commitlintrc.yaml",
        ".czrc",
        ".cz.toml",
        ".cz.json",
        ".cz.yaml",
    }
)

_DCO_RE = re.compile(
    r"developer certificate of origin|signed-off-by|git commit\s+-s\b|--signoff\b|\bDCO\b",
    re.I,
)
_CLA_RE = re.compile(
    r"contributor licen[sc]e agreement|\bCLA\b|cla-assistant|contributor-assistant/github-action",
    re.I,
)
_CONVENTION_RE = re.compile(
    r"conventional commits|conventionalcommits\.org|commitlint|commitizen",
    re.I,
)


def _norm(path: str) -> str:
    return "/" + path.replace("\\", "/").lstrip("/")


def _line_of(content: str, pos: int) -> int:
    return content.count("\n", 0, pos) + 1


def _in_health_location(path: str) -> bool:
    norm = _norm(path)
    parent = norm.rsplit("/", 1)[0] + "/"
    return parent in _HEALTH_DIRS


def _presence_kind(path: str) -> str | None:
    """Classify a path as a known community-health file, else ``None``."""
    norm = _norm(path).lower()
    base = norm.rsplit("/", 1)[-1]

    # Template folders — a project may keep several PR / issue templates together.
    if "/.github/pull_request_template/" in norm and base.endswith((".md", ".rst")):
        return "pr-template"
    if "/.github/issue_template/" in norm and base.endswith((".md", ".yml", ".yaml")):
        return "issue-template"
    # Single-file templates — the name is specific enough to match anywhere.
    if base in (
        "pull_request_template.md",
        "pull_request_template.rst",
        "pull_request_template.txt",
    ):
        return "pr-template"
    if base == "issue_template.md":
        return "issue-template"

    # The remaining files only count in a recognised community-health location.
    if not _in_health_location(path):
        return None
    if base in ("contributing.md", "contributing.rst", "contributing.txt", "contributing"):
        return "guide"
    if base in ("code_of_conduct.md", "code_of_conduct.rst", "code-of-conduct.md"):
        return "code-of-conduct"
    if base == "codeowners":
        return "codeowners"
    if base in ("security.md", "security.rst"):
        return "security"
    return None


def _is_text_signal_file(path: str) -> bool:
    """Whether DCO / CLA / commit-convention prose may be trusted in this file.

    Restricting the content scan to the files those rules actually live in keeps
    a "Signed-off-by" sitting in a source-code comment from being mistaken for a
    project-wide DCO requirement.
    """
    norm = _norm(path).lower()
    base = norm.rsplit("/", 1)[-1]
    if base in (
        "readme.md",
        "readme.rst",
        "contributing.md",
        "contributing.rst",
        "contributing.txt",
        "contributing",
        "code_of_conduct.md",
    ):
        return True
    if base.startswith("pull_request_template") or base == "issue_template.md":
        return True
    if "/.github/pull_request_template/" in norm or "/.github/issue_template/" in norm:
        return True
    if "/.github/workflows/" in norm and base.endswith((".yml", ".yaml")):
        return True
    if base in ("package.json", ".pre-commit-config.yaml", ".pre-commit-config.yml"):
        return True
    if base in _COMMIT_CONFIG:
        return True
    if base in ("dco.yml", "dco.yaml", "cla.yml", "cla.yaml"):
        return True
    return False


def find_contribution_guide(file_contents: dict[str, str]) -> dict:
    """Map what a project requires of a contributor before it accepts a change.

    Args:
        file_contents: mapping of path to file text (as CodeABC already read it).

    Returns ``{"has_guide", "requirements", "notes"}`` where each requirement is
    ``{"kind", "label_zh", "detail_zh", "path", "line"}`` (``line`` is ``0`` for a
    plain presence signal, or the line of the matched text for DCO / CLA /
    commit-convention prose).
    """
    found: dict[str, dict] = {}  # kind -> {"path", "line", "depth"}

    def record(kind: str, path: str, line: int = 0) -> None:
        depth = _norm(path).count("/")
        prev = found.get(kind)
        if prev is None or depth < prev["depth"]:
            found[kind] = {"path": path, "line": line, "depth": depth}

    for path, content in file_contents.items():
        norm = _norm(path).lower()
        base = norm.rsplit("/", 1)[-1]

        kind = _presence_kind(path)
        if kind:
            record(kind, path)
        if base in _COMMIT_CONFIG:
            record("commit-convention", path)
        if base in ("dco.yml", "dco.yaml") and "/.github/" in norm:
            record("dco", path)
        if base in ("cla.yml", "cla.yaml") and "/.github/" in norm:
            record("cla", path)

        if content and _is_text_signal_file(path):
            for signal, rx in (
                ("dco", _DCO_RE),
                ("cla", _CLA_RE),
                ("commit-convention", _CONVENTION_RE),
            ):
                match = rx.search(content)
                if match:
                    record(signal, path, _line_of(content, match.start()))

    requirements = [
        {
            "kind": kind,
            "label_zh": _LABELS[kind],
            "detail_zh": _DETAIL[kind],
            "path": found[kind]["path"],
            "line": found[kind]["line"],
        }
        for kind in _ORDER
        if kind in found
    ]
    return {
        "has_guide": "guide" in found,
        "requirements": requirements,
        "notes": _build_notes(found),
    }


def _build_notes(found: dict[str, dict]) -> list[str]:
    notes: list[str] = []
    if not found:
        return notes
    if "guide" not in found:
        notes.append(
            "没找到 CONTRIBUTING 贡献指南文件，参与方式可能写在 README 里，或得直接问维护者。"
        )
    blockers = [k for k in ("dco", "cla", "commit-convention") if k in found]
    if blockers:
        names = "、".join(_LABELS[k] for k in blockers)
        notes.append(f"提交前尤其注意：{names}——这几项最容易让第一次 PR 在还没被看代码前就被打回。")
    if "codeowners" in found:
        notes.append("有 CODEOWNERS，改动需要对应负责人审查通过，找对审查人能少等很久。")
    return notes


def render_contributing_markdown(project_name: str, data: dict | None) -> str:
    """Render the contribution map as Markdown, or ``""`` if nothing was found."""
    requirements = (data or {}).get("requirements") or []
    if not requirements:
        return ""

    lines = [
        f"# {project_name} — 怎么给这个项目贡献代码",
        "",
        "> 想把自己的改动提给这个项目，又怕一上来就踩流程的坑被打回？下面这些是它对贡献者的"
        "要求，全部来自项目里现成的“社区规范”文件。提 PR 前照着对一遍，基本就不会卡在流程上。",
        "",
        "## 提交改动前，先满足这几项",
    ]
    for req in requirements:
        loc = f"`{req['path']}`"
        if req.get("line"):
            loc += f" 第 {req['line']} 行"
        lines.append(f"- **{req['label_zh']}**（{loc}）：{req['detail_zh']}")

    notes = (data or {}).get("notes") or []
    if notes:
        lines.append("")
        lines.append("## 一句话提醒")
        for note in notes:
            lines.append(f"- {note}")
    return "\n".join(lines).rstrip() + "\n"
