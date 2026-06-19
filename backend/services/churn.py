"""Git-history churn analysis: change hotspots and co-change coupling.

This is a *dynamic* signal — how the code actually evolved over time — and
is deliberately independent of the static import graph in ``importgraph``.
A file that changes in many commits, or that almost always changes together
with another file, is where review attention and refactoring tend to pay
off, regardless of how the modules import one another.

The parsing core (:func:`analyze_churn`) is pure: it operates on the text of
``git log --numstat`` so it can be unit-tested with fixture strings and no
real repository. :func:`collect_git_log` is the thin, side-effecting wrapper
that actually shells out to git.
"""

from __future__ import annotations

import subprocess
from collections import defaultdict
from itertools import combinations
from pathlib import Path

_COMMIT_MARKER = "::C::"

# Commits touching more than this many files are almost always bulk events
# (mass renames, auto-formatting, vendored drops). They inflate every file's
# co-change count without expressing real coupling, so we still count each
# file's change frequency but skip generating co-change pairs for them.
_MAX_FILES_FOR_COUPLING = 25


def collect_git_log(repo_path: Path, *, max_commits: int = 2000) -> str | None:
    """Return ``git log --numstat`` text for *repo_path*, or ``None``.

    ``None`` means "no usable history" — the path is not a git work tree, git
    is unavailable, or the command failed. Callers treat that as "churn
    analysis unavailable" rather than an error, so an uploaded (non-git)
    project simply gets empty churn results.
    """
    if not (repo_path / ".git").exists():
        return None
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repo_path),
                "log",
                "--no-merges",
                f"--max-count={max_commits}",
                "--numstat",
                f"--format={_COMMIT_MARKER}%H::%at::%an",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            errors="replace",
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _normalize_path(raw: str) -> str:
    """Resolve git rename syntax to the post-rename path.

    Git renders renames in ``--numstat`` as ``dir/{old => new}/file.py`` or as
    the plain ``old.py => new.py``. We fold history onto the *current* path so
    a file's churn survives a rename.
    """
    raw = raw.strip()
    if "=>" not in raw:
        return raw
    if "{" in raw and "}" in raw:
        head, _, rest = raw.partition("{")
        inner, _, tail = rest.partition("}")
        _, _, new = inner.partition("=>")
        combined = (head + new.strip() + tail).replace("//", "/")
        return combined.strip("/") or combined.strip()
    _, _, new = raw.partition("=>")
    return new.strip()


def _hotspot_reason(commits: int, authors: int) -> str:
    if commits >= 10 and authors >= 3:
        return (
            f"改了 {commits} 次、{authors} 个人动过，是最活跃也最容易出 bug 的地方，"
            "回归测试要重点盖。"
        )
    if commits >= 10:
        return f"改了 {commits} 次但基本一个人在维护，逻辑集中、值得补文档和测试。"
    return f"改了 {commits} 次，是相对活跃的文件，读代码时优先关注。"


def _coupling_reason(ratio: int) -> str:
    if ratio >= 70:
        return f"{ratio}% 的改动里两者一起变，耦合很强，多半该一起读、考虑合并或抽公共层。"
    return f"约 {ratio}% 的改动里两者一起变，存在隐性耦合，改一个时别忘了看另一个。"


def analyze_churn(
    git_log_text: str | None,
    *,
    scanned_paths: set[str] | list[str] | None = None,
    limit: int = 8,
    min_coupling_support: int = 3,
) -> dict:
    """Parse ``git log --numstat`` text into change hotspots and coupling.

    Args:
        git_log_text: output of :func:`collect_git_log` (``None`` ⇒ empty result).
        scanned_paths: if given, only these paths are considered, so churn lines
            up with the files CodeABC actually scanned (drops lockfiles, deleted
            files, binaries the analysis never showed).
        limit: how many hotspots / couplings to return.
        min_coupling_support: a pair must co-change at least this many times to
            count, filtering out one-off coincidences.

    Returns ``{"hotspots", "couplings", "commits_analyzed"}`` where ``hotspots``
    is sorted by commit count and ``couplings`` by co-change count.
    """
    allowed: set[str] | None = set(scanned_paths) if scanned_paths is not None else None

    commit_count: dict[str, int] = defaultdict(int)
    lines_changed: dict[str, int] = defaultdict(int)
    authors: dict[str, set[str]] = defaultdict(set)
    pair_count: dict[tuple[str, str], int] = defaultdict(int)
    commits_analyzed = 0

    current_author = ""
    touched: set[str] = set()

    def _flush(files: set[str]) -> None:
        if not files:
            return
        nonlocal commits_analyzed
        commits_analyzed += 1
        if len(files) <= _MAX_FILES_FOR_COUPLING:
            for a, b in combinations(sorted(files), 2):
                pair_count[(a, b)] += 1

    for line in (git_log_text or "").splitlines():
        if line.startswith(_COMMIT_MARKER):
            _flush(touched)
            touched = set()
            parts = line[len(_COMMIT_MARKER) :].split("::")
            current_author = parts[2] if len(parts) >= 3 else ""
            continue
        if not line.strip():
            continue
        cols = line.split("\t")
        if len(cols) != 3:
            continue
        added, deleted, raw_path = cols
        path = _normalize_path(raw_path)
        if not path or (allowed is not None and path not in allowed):
            continue
        if path not in touched:
            touched.add(path)
            commit_count[path] += 1
            authors[path].add(current_author)
        for value in (added, deleted):
            if value.isdigit():
                lines_changed[path] += int(value)
    _flush(touched)

    hotspots = [
        {
            "path": path,
            "commits": commits,
            "lines_changed": lines_changed[path],
            "authors": len(authors[path]),
            "reason": _hotspot_reason(commits, len(authors[path])),
        }
        for path, commits in commit_count.items()
        if commits >= 2
    ]
    hotspots.sort(key=lambda h: (-h["commits"], -h["lines_changed"], h["path"]))

    couplings = []
    for (a, b), co in pair_count.items():
        if co < min_coupling_support:
            continue
        base = min(commit_count[a], commit_count[b])
        if base == 0:
            continue
        ratio = round(co / base * 100)
        couplings.append(
            {
                "file_a": a,
                "file_b": b,
                "co_changes": co,
                "coupling": ratio,
                "reason": _coupling_reason(ratio),
            }
        )
    couplings.sort(key=lambda c: (-c["co_changes"], -c["coupling"], c["file_a"]))

    return {
        "hotspots": hotspots[:limit],
        "couplings": couplings[:limit],
        "commits_analyzed": commits_analyzed,
    }
