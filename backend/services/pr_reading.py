"""Pull-request reading mode: turn a PR link into a plain-language diff walkthrough.

Deterministic core, no LLM call: fetch the unified diff, break it into
per-file changes, classify each file's change type, and propose a reading
order. An LLM explanation layer can sit on top of this payload later.
"""

from __future__ import annotations

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
