"""Pull-request reading mode: turn a PR link into a plain-language diff walkthrough.

Deterministic core, no LLM call: fetch the unified diff, break it into
per-file changes, classify each file's change type, and propose a reading
order. An LLM explanation layer can sit on top of this payload later.
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
import urllib.request
from dataclasses import dataclass, field

_PR_URL_RE = re.compile(r"^https?://(?:www\.)?github\.com/([^/]+)/([^/]+)/pull/(\d+)(?:/[^\s]*)?$")


@dataclass
class PrRef:
    owner: str
    repo: str
    number: int


@dataclass
class FileChange:
    path: str
    added: int
    deleted: int
    change_type: str  # code | test | docs | config | other
    hunks: list[str] = field(default_factory=list)


def parse_pr_url(url: str) -> PrRef:
    """Parse https://github.com/owner/repo/pull/123 (any suffix after the number)."""
    match = _PR_URL_RE.match(url.strip())
    if not match:
        raise ValueError(f"not a GitHub pull request URL: {url}")
    owner, repo, number = match.group(1), match.group(2), int(match.group(3))
    return PrRef(owner=owner, repo=repo.removesuffix(".git"), number=number)


def fetch_pr_diff(ref: PrRef, timeout: float = 30.0) -> str:
    """Fetch the PR's unified diff. Try gh first (auth'd), fall back to patch-diff URL."""
    try:
        result = subprocess.run(
            ["gh", "pr", "diff", str(ref.number), "--repo", f"{ref.owner}/{ref.repo}"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout
    except (OSError, subprocess.TimeoutExpired):
        pass
    url = f"https://patch-diff.githubusercontent.com/raw/{ref.owner}/{ref.repo}/pull/{ref.number}.diff"
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 (fixed host)
        return resp.read().decode("utf-8", errors="replace")


_FILE_KIND_RULES: tuple[tuple[str, str], ...] = (
    ("test", "test"),
    ("docs", "docs"),
    ("config", "config"),
)


def _file_kind(path: str) -> str:
    p = path.lower()
    name = p.rsplit("/", 1)[-1]
    if any(
        tok in p for tok in ("/tests/", "/test/", "test_", "_test.", ".test.", ".spec.")
    ) or name.startswith(("test_", "tests_")):
        return "test"
    if name.endswith((".md", ".rst", ".txt")) or p.startswith(("docs/", "doc/")):
        return "docs"
    if name.endswith((".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".lock")) or name in {
        "dockerfile",
        "makefile",
        "justfile",
    }:
        return "config"
    return "code"


def parse_diff_files(diff_text: str) -> list[FileChange]:
    """Break a unified diff into per-file changes with add/del counts."""
    files: list[FileChange] = []
    current: FileChange | None = None
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            if current is not None:
                files.append(current)
            match = re.match(r"diff --git a/(\S+) b/(\S+)", line)
            path = match.group(2) if match else "unknown"
            current = FileChange(path=path, added=0, deleted=0, change_type=_file_kind(path))
        elif current is not None:
            if line.startswith("@@"):
                current.hunks.append(line)
            elif line.startswith("+") and not line.startswith("+++"):
                current.added += 1
            elif line.startswith("-") and not line.startswith("---"):
                current.deleted += 1
    if current is not None:
        files.append(current)
    return files


def reading_order(files: list[FileChange]) -> list[FileChange]:
    """Suggest a review order: biggest production-code diffs first, then tests, then docs/config."""
    rank = {"code": 0, "test": 1, "config": 2, "docs": 3, "other": 4}
    return sorted(
        files,
        key=lambda f: (rank.get(f.change_type, 4), -(f.added + f.deleted), f.path),
    )


def summarize_diff(files: list[FileChange]) -> dict:
    """Plain-language rollup of what the PR touches, no LLM needed."""
    by_kind: dict[str, int] = {}
    for f in files:
        by_kind[f.change_type] = by_kind.get(f.change_type, 0) + 1
    total_added = sum(f.added for f in files)
    total_deleted = sum(f.deleted for f in files)
    biggest = max(files, key=lambda f: f.added + f.deleted) if files else None
    return {
        "file_count": len(files),
        "by_kind": by_kind,
        "total_added": total_added,
        "total_deleted": total_deleted,
        "biggest_file": biggest.path if biggest else None,
    }


def analyze_pr(url: str) -> dict:
    """Full pipeline: URL -> diff -> per-file breakdown with a suggested reading order."""
    ref = parse_pr_url(url)
    diff_text = fetch_pr_diff(ref)
    files = parse_diff_files(diff_text)
    ordered = reading_order(files)
    return {
        "url": url,
        "owner": ref.owner,
        "repo": ref.repo,
        "number": ref.number,
        "summary": summarize_diff(files),
        "files": [
            {
                "path": f.path,
                "added": f.added,
                "deleted": f.deleted,
                "change_type": f.change_type,
                "hunks": f.hunks,
            }
            for f in ordered
        ],
    }


def render_markdown(analysis: dict) -> str:
    """Human-readable walkthrough of the analysis payload."""
    summary = analysis["summary"]
    lines = [
        f"# PR reading: {analysis['owner']}/{analysis['repo']}#{analysis['number']}",
        "",
        (
            f"{summary['file_count']} files touched "
            f"(+{summary['total_added']} / -{summary['total_deleted']}). "
            + ", ".join(f"{kind}: {count}" for kind, count in sorted(summary["by_kind"].items()))
        ),
        "",
        "## Suggested reading order",
    ]
    for i, f in enumerate(analysis["files"], start=1):
        lines.append(f"{i}. `{f['path']}` ({f['change_type']}, +{f['added']} / -{f['deleted']})")
    return "\n".join(lines) + "\n"


def to_json(analysis: dict) -> str:
    return json.dumps(analysis, ensure_ascii=False, indent=2)


_EXPLAIN_MAX_FILES = 8
_DIFF_EXCERPT_MAX_LINES = 120

_SYMBOL_RE = re.compile(
    r"^\+\s*(?:async\s+def|def|class|function|export\s+(?:async\s+)?function|export\s+class)\s+([A-Za-z_][\w]*)"
)


def _diff_sections(diff_text: str) -> dict[str, list[str]]:
    """Map each file path to its raw diff lines (headers + hunks)."""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            match = re.match(r"diff --git a/(\S+) b/(\S+)", line)
            current = match.group(2) if match else None
            if current is not None:
                sections[current] = [line]
        elif current is not None:
            sections[current].append(line)
    return sections


def _symbols_from_excerpt(excerpt_lines: list[str]) -> list[str]:
    names: list[str] = []
    for line in excerpt_lines:
        m = _SYMBOL_RE.match(line)
        if m and m.group(1) not in names:
            names.append(m.group(1))
    return names


def _deterministic_note(change: FileChange, excerpt_lines: list[str]) -> str:
    """Plain-language note without any LLM: what kind of file it is, its size, and the
    functions/classes it adds or updates (from added definition lines in the diff)."""
    symbols = _symbols_from_excerpt(excerpt_lines)
    base = {
        "code": "production code",
        "test": "test",
        "docs": "documentation",
        "config": "configuration",
    }.get(change.change_type, "other")
    size = f"+{change.added} / -{change.deleted} lines"
    if symbols:
        return f"This {base} file ({size}) adds or updates: {', '.join(symbols[:6])}."
    return f"This {base} file ({size}) is edited; open it to see the exact changes."


def _excerpt(lines: list[str]) -> str:
    if len(lines) <= _DIFF_EXCERPT_MAX_LINES:
        return "\n".join(lines)
    head = "\n".join(lines[:_DIFF_EXCERPT_MAX_LINES])
    return head + f"\n... ({len(lines) - _DIFF_EXCERPT_MAX_LINES} more diff lines trimmed)"


async def explain_files(
    files: list[FileChange],
    diff_text: str,
    *,
    api_key: str | None = None,
    model: str | None = None,
) -> dict[str, str]:
    """Plain-language note per file. LLM-backed when a key is configured; otherwise a
    deterministic note built from the diff itself, so the feature works key-free."""
    from backend.services.llm import call_llm, is_error_text

    sections = _diff_sections(diff_text)
    out: dict[str, str] = {}

    async def explain_one(change: FileChange) -> tuple[str, str]:
        excerpt_lines = sections.get(change.path, [])
        excerpt = _excerpt(excerpt_lines)
        fallback = _deterministic_note(change, excerpt_lines)
        if not api_key:
            return change.path, fallback
        prompt = (
            "You are explaining one file's part of a pull request to someone who does not code.\n"
            f"File: {change.path} ({change.change_type}, +{change.added} / -{change.deleted}).\n"
            f"Diff excerpt:\n{excerpt}\n\n"
            "In 2-3 plain sentences: what changed in this file and why it might matter. "
            "No jargon; say the file name, not the path, when you refer to it."
        )
        text = (await call_llm(prompt, api_key=api_key, model=model)).strip()
        if not text or is_error_text(text):
            return change.path, fallback
        return change.path, text

    ordered = files[:_EXPLAIN_MAX_FILES]
    results = await asyncio.gather(*(explain_one(f) for f in ordered))
    out.update(results)
    # Files beyond the cap still get the deterministic note so the UI never shows a gap.
    for f in files[_EXPLAIN_MAX_FILES:]:
        out[f.path] = _deterministic_note(f, sections.get(f.path, []))
    return out


async def analyze_pr_explained(
    url: str, *, explain: bool, api_key: str | None = None, model: str | None = None
) -> dict:
    """analyze_pr plus optional per-file explanations (LLM when keyed, deterministic otherwise)."""
    ref = parse_pr_url(url)
    diff_text = await asyncio.to_thread(fetch_pr_diff, ref)
    files = parse_diff_files(diff_text)
    ordered = reading_order(files)
    analysis = {
        "url": url,
        "owner": ref.owner,
        "repo": ref.repo,
        "number": ref.number,
        "summary": summarize_diff(files),
        "files": [
            {
                "path": f.path,
                "added": f.added,
                "deleted": f.deleted,
                "change_type": f.change_type,
                "hunks": f.hunks,
            }
            for f in ordered
        ],
    }
    if explain:
        analysis["explanations"] = await explain_files(
            ordered, diff_text, api_key=api_key, model=model
        )
    return analysis
