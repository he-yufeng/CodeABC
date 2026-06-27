"""Release & versioning map — how this project ships new versions, and how you
would know what changed.

The CI map answers "what gets checked before my change is let in"; the
scheduled-tasks map answers "what runs on a timer". This answers the question a
newcomer asks while sizing up an unfamiliar project: **is this thing alive, what
version am I looking at, and when the authors ship something new, where do I look
to see what changed and how do I get it?** Three plain facts settle most of that
worry — the current version number, whether there is a changelog, and how a new
release actually goes out — and all three are sitting in files CodeABC already
read.

It is pure over the file contents — no LLM, nothing run — and recognises the
version sources and release pipelines people reach for most:

  current version   pyproject.toml / package.json / Cargo.toml / setup.py /
                    setup.cfg / a VERSION file / ``__version__`` / pom.xml /
                    build.gradle
  changelog         CHANGELOG / HISTORY / NEWS / RELEASES (+ "Keep a Changelog")
  release pipeline  GitHub Actions / GitLab CI publishing to PyPI, npm, a GitHub
                    Release, crates.io, RubyGems, or a Docker image — on a tag
                    push or a published release

Every term is glossed in plain Chinese (语义化版本 / 日历版本 / 更新日志 /
推送 git tag 时自动发布) so a non-programmer can read the row without knowing what
semver or ``twine`` are.

:func:`find_release_info` is pure over the file contents, so it is unit-testable
with plain strings and needs no repository.

Limitations (kept honest on purpose):

  * Signature based, not a build-system evaluation. A version computed at build
    time (``setuptools-scm``, ``hatch-vcs``) is reported as "derived from git
    tags" rather than resolved to a number; an exotic manifest or a hand-rolled
    release shell script this module does not recognise is missed.
  * Only the first, most authoritative version source is reported as *the*
    version, so a repository that pins different numbers in different manifests
    shows the highest-priority one, not all of them.
  * Whether a changelog is actually kept current is not judged — only that one
    exists and roughly what shape it takes.
"""

from __future__ import annotations

import re

# --- versioning scheme ------------------------------------------------------

_PRERELEASE_RE = re.compile(r"(?:\d|[-._])(rc|alpha|beta|preview|pre|dev|nightly|a|b|c)\d*\b", re.I)


def _classify_scheme(version: str) -> tuple[str, str]:
    """Return ``(scheme, plain-Chinese label)`` for a version string."""
    v = version.strip().lstrip("vV")
    if not v:
        return "", ""
    if "-" in v or "+" in v or _PRERELEASE_RE.search(v):
        return "prerelease", "预发布版本（带 rc/beta/dev 等后缀，还不是正式版）"
    if re.match(r"^(19|20)\d\d[._-]\d", v):
        return "calver", "日历版本（用年份/日期编号，而不是主次修订）"
    if re.match(r"^\d+\.\d+\.\d+$", v):
        if v.startswith("0."):
            return "zerover", "0.x 早期版本（还没到 1.0，接口可能随时变动）"
        return "semver", "语义化版本（主版本.次版本.修订号）"
    if re.match(r"^\d+\.\d+$", v):
        return "twopart", "两段版本号（主版本.次版本）"
    if re.match(r"^\d+$", v):
        return "single", "单一递增版本号"
    return "other", "自定义版本号格式"


# --- current version --------------------------------------------------------

_DYNAMIC_RE = re.compile(r"dynamic\s*=\s*\[[^\]]*[\"']version[\"']", re.I)
_SCM_RE = re.compile(r"setuptools[_-]scm|hatch-vcs|versioningit|dunamai", re.I)

_SOURCE_LABEL = {
    "pyproject": "pyproject.toml",
    "package-json": "package.json",
    "cargo": "Cargo.toml",
    "setup-py": "setup.py",
    "setup-cfg": "setup.cfg",
    "version-file": "VERSION 文件",
    "dunder": "代码里的 __version__",
    "pom": "pom.xml",
    "gradle": "build.gradle",
}

# Most authoritative manifest first.
_SOURCE_PRIORITY = (
    "pyproject",
    "package-json",
    "cargo",
    "setup-py",
    "setup-cfg",
    "version-file",
    "dunder",
    "pom",
    "gradle",
)


def _version_from_file(base: str, content: str) -> tuple[str, str] | None:
    """Return ``(kind, version)`` for a recognised manifest, else ``None``."""
    if base == "pyproject.toml":
        m = re.search(r"(?m)^\s*version\s*=\s*[\"']([0-9][^\"']*)[\"']", content)
        return ("pyproject", m.group(1)) if m else None
    if base == "package.json":
        m = re.search(r"\"version\"\s*:\s*\"([0-9][^\"]*)\"", content)
        return ("package-json", m.group(1)) if m else None
    if base == "cargo.toml":
        m = re.search(r"(?ms)^\[package\].*?^\s*version\s*=\s*\"([0-9][^\"]*)\"", content)
        return ("cargo", m.group(1)) if m else None
    if base == "setup.py":
        m = re.search(r"version\s*=\s*[\"']([0-9][^\"']*)[\"']", content)
        return ("setup-py", m.group(1)) if m else None
    if base == "setup.cfg":
        m = re.search(r"(?m)^\s*version\s*=\s*([0-9]\S*)\s*$", content)
        return ("setup-cfg", m.group(1)) if m else None
    if base in ("version", "version.txt"):
        first = content.strip().splitlines()[0].strip() if content.strip() else ""
        return ("version-file", first.lstrip("vV")) if re.match(r"^v?[0-9]", first) else None
    if base == "pom.xml":
        m = re.search(r"<version>\s*([0-9][^<]*)</version>", content)
        return ("pom", m.group(1).strip()) if m else None
    if base in ("build.gradle", "build.gradle.kts"):
        m = re.search(r"(?m)^\s*version\s*=?\s*[\"']([0-9][^\"']*)[\"']", content)
        return ("gradle", m.group(1)) if m else None
    return None


def _find_version(file_contents: dict[str, str]) -> tuple[str, str, str, bool]:
    """Return ``(version, source_path, source_kind, dynamic_from_vcs)``."""
    dynamic = False
    candidates: dict[str, tuple[str, str]] = {}  # kind -> (version, path)

    for path, content in file_contents.items():
        if not content:
            continue
        base = path.rsplit("/", 1)[-1].lower()

        if base == "pyproject.toml" and (_DYNAMIC_RE.search(content) or _SCM_RE.search(content)):
            dynamic = True

        hit = _version_from_file(base, content)
        if hit and hit[0] not in candidates:
            candidates[hit[0]] = (hit[1], path)

        if base.endswith(".py") and "dunder" not in candidates:
            m = re.search(r"(?m)^__version__\s*=\s*[\"']([0-9][^\"']*)[\"']", content)
            if m:
                candidates["dunder"] = (m.group(1), path)

    for kind in _SOURCE_PRIORITY:
        if kind in candidates:
            version, path = candidates[kind]
            return version, path, kind, dynamic
    return "", "", "", dynamic


# --- changelog --------------------------------------------------------------

_CHANGELOG_NAMES = frozenset(
    {
        "changelog",
        "changelog.md",
        "changelog.rst",
        "changelog.txt",
        "changes",
        "changes.md",
        "changes.rst",
        "history.md",
        "history.rst",
        "history.txt",
        "news",
        "news.md",
        "news.rst",
        "releases.md",
        "release-notes.md",
        "release_notes.md",
    }
)


def _find_changelog(file_contents: dict[str, str]) -> tuple[str, str, str]:
    """Return ``(path, style, plain-Chinese label)`` for the shallowest changelog."""
    best: tuple[int, str, str] | None = None
    for path, content in file_contents.items():
        base = path.rsplit("/", 1)[-1].lower()
        if base not in _CHANGELOG_NAMES:
            continue
        depth = path.count("/")
        if best is None or depth < best[0]:
            best = (depth, path, content or "")
    if best is None:
        return "", "none", ""
    _, path, content = best
    low = content.lower()
    if "keep a changelog" in low or "keepachangelog.com" in low or "## [unreleased]" in low:
        label = "遵循 Keep a Changelog 规范：按版本分节，最上面是还没发布的改动"
        return path, "keepachangelog", label
    if re.search(r"(?m)^#{1,3}\s*\[?v?\d+\.\d+", content):
        return path, "versioned", "按版本号分节，记录每个版本改了什么"
    return path, "freeform", "有更新日志文件，但不是标准的分节格式"


# --- release automation -----------------------------------------------------

_PUBLISH_SIGNS = (
    (
        re.compile(
            r"gh-action-pypi-publish|twine\s+upload|poetry\s+publish|flit\s+publish|hatch\s+publish",
            re.I,
        ),
        "PyPI",
    ),
    (re.compile(r"npm\s+publish|npm-publish|yarn\s+publish|pnpm\s+publish", re.I), "npm"),
    (
        re.compile(
            r"action-gh-release|actions/create-release|gh\s+release\s+create|release-action",
            re.I,
        ),
        "GitHub Release",
    ),
    (re.compile(r"cargo\s+publish", re.I), "crates.io"),
    (re.compile(r"gem\s+push|setup-ruby.*gem|rubygems", re.I), "RubyGems"),
    (re.compile(r"docker/build-push-action|docker\s+push", re.I), "Docker 镜像"),
)

_SYSTEM_LABEL = {"github-actions": "GitHub Actions", "gitlab-ci": "GitLab CI"}


def _release_system(path: str) -> str | None:
    p = path.lower()
    if p.startswith(".github/workflows/") and p.endswith((".yml", ".yaml")):
        return "github-actions"
    if p.endswith(".gitlab-ci.yml") or p == ".gitlab-ci.yml":
        return "gitlab-ci"
    return None


def _release_trigger(content: str) -> tuple[str, str]:
    """Plain-Chinese gloss of what kicks off a release pipeline."""
    if re.search(r"(?m)^\s*release\s*:", content) and re.search(r"types\s*:", content):
        return "release", "发布一个 GitHub Release 时"
    if re.search(r"(?m)^\s*tags\s*:", content) or re.search(r"push:\s*\n\s*tags", content):
        return "tag-push", "推送 git tag 时"
    if re.search(r"(?m)^\s*workflow_dispatch\s*:", content):
        return "manual", "维护者手动触发"
    return "", ""


def _line_of(content: str, pos: int) -> int:
    return content.count("\n", 0, pos) + 1


def _build_notes(
    version: str, vkind: str, dynamic: bool, cl_style: str, publish_targets: list[str]
) -> list[str]:
    notes: list[str] = []
    if version:
        notes.append(f"当前版本号 {version}，来自 {_SOURCE_LABEL.get(vkind, vkind)}。")
    elif dynamic:
        notes.append(
            "版本号在打包时由 git tag 自动推导"
            "（setuptools-scm / hatch-vcs 一类），仓库里没有写死的数字。"
        )
    else:
        notes.append("没找到写明的版本号，可能还没开始正式做版本管理，或用了本工具不认识的方式。")
    if cl_style == "none":
        notes.append("没有更新日志文件，想知道两版之间改了什么，得去翻提交记录或 Release 页面。")
    if publish_targets:
        notes.append(
            "发布渠道："
            + "、".join(publish_targets)
            + "（由 CI 自动完成，维护者一般只需打个版本标签）。"
        )
    return notes


def find_release_info(file_contents: dict[str, str]) -> dict:
    """Map how a project versions and ships itself.

    Args:
        file_contents: mapping of path to file text (as CodeABC already read it).

    Returns ``{"version", "version_source", "version_source_kind",
    "dynamic_from_vcs", "scheme", "scheme_zh", "changelog_path",
    "changelog_style", "changelog_style_zh", "automation", "publish_targets",
    "notes"}`` where each automation entry is
    ``{"trigger", "trigger_zh", "target", "path", "line"}``.
    """
    version, vsource, vkind, dynamic = _find_version(file_contents)
    scheme, scheme_zh = _classify_scheme(version)
    cl_path, cl_style, cl_zh = _find_changelog(file_contents)

    automation: list[dict] = []
    seen: set[tuple] = set()
    for path, content in file_contents.items():
        if not content or _release_system(path) is None:
            continue
        trigger, trigger_zh = _release_trigger(content)
        for rx, target in _PUBLISH_SIGNS:
            match = rx.search(content)
            if not match:
                continue
            key = (path, target)
            if key in seen:
                continue
            seen.add(key)
            automation.append(
                {
                    "trigger": trigger,
                    "trigger_zh": trigger_zh,
                    "target": target,
                    "path": path,
                    "line": _line_of(content, match.start()),
                }
            )
    automation.sort(key=lambda a: (a["path"], a["line"]))

    publish_targets: list[str] = []
    for entry in automation:
        if entry["target"] not in publish_targets:
            publish_targets.append(entry["target"])

    return {
        "version": version,
        "version_source": vsource,
        "version_source_kind": vkind,
        "dynamic_from_vcs": dynamic,
        "scheme": scheme,
        "scheme_zh": scheme_zh,
        "changelog_path": cl_path,
        "changelog_style": cl_style,
        "changelog_style_zh": cl_zh,
        "automation": automation,
        "publish_targets": publish_targets,
        "notes": _build_notes(version, vkind, dynamic, cl_style, publish_targets),
    }


def render_release_markdown(project_name: str, data: dict | None) -> str:
    """Render the release & versioning map as Markdown, or ``""`` if empty."""
    data = data or {}
    version = data.get("version") or ""
    dynamic = bool(data.get("dynamic_from_vcs"))
    changelog_path = data.get("changelog_path") or ""
    automation = data.get("automation") or []
    if not version and not dynamic and not changelog_path and not automation:
        return ""

    lines = [
        f"# {project_name} — 版本与发布地图",
        "",
        "> 想知道这个项目“现在是第几版、出新版本时去哪看改了什么、新版又是怎么发出去的”，"
        "看这一页就够。下面三件事基本说清楚：当前版本号、有没有更新日志、发布是怎么自动跑的。",
        "",
        "## 当前版本",
    ]
    if version:
        src = _SOURCE_LABEL.get(data.get("version_source_kind", ""), data.get("version_source", ""))
        lines.append(f"- **{version}**（写在 `{src}` 里）")
        if data.get("scheme_zh"):
            lines.append(f"- 版本号规则：{data['scheme_zh']}")
    elif dynamic:
        lines.append("- 版本号由 git tag 在打包时自动推导（仓库里没有写死的数字）")
    else:
        lines.append("- 没找到写明的版本号")

    lines.append("")
    lines.append("## 更新日志（去哪看每版改了什么）")
    if changelog_path:
        lines.append(f"- `{changelog_path}` — {data.get('changelog_style_zh', '')}")
    else:
        lines.append("- 没有更新日志文件；只能去翻提交记录或项目的 Release 页面")

    if automation:
        lines.append("")
        lines.append("## 新版本怎么发出去（自动发布流水线）")
        current_path = None
        for entry in automation:
            if entry["path"] != current_path:
                current_path = entry["path"]
                system = _SYSTEM_LABEL.get(_release_system(current_path) or "", "")
                head = f"### `{current_path}`"
                if system:
                    head += f" · {system}"
                if entry["trigger_zh"]:
                    head += f" — {entry['trigger_zh']}"
                lines.append(head)
            lines.append(f"- 发布到 **{entry['target']}**  第 {entry['line']} 行")

    notes = data.get("notes") or []
    if notes:
        lines.append("")
        lines.append("## 一句话总结")
        for note in notes:
            lines.append(f"- {note}")

    return "\n".join(lines).rstrip() + "\n"
