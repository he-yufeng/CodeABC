"""Code ownership and knowledge-silo analysis from git history.

Churn says *how often* a file changes; ownership says *who* changes it. The
two are independent dynamic signals: a file can be a quiet corner that only one
person has ever touched (a knowledge silo — risky if they leave) without being
a churn hotspot at all.

For each file we derive, from the author of every commit that touched it:

* the primary author and how much of the history they own (a percentage),
* how many distinct authors have touched it,
* the *bus factor* — the smallest number of authors who together account for a
  majority of the commits. A bus factor of 1 means a single person holds the
  majority of the knowledge for that file.

:func:`analyze_ownership` is pure: it parses the same ``git log --numstat``
text that :func:`churn.collect_git_log` already produces, so it is unit-testable
with fixture strings and needs no real repository. We deliberately re-parse that
text rather than coupling to churn's internals, keeping the two analyses
independent.
"""

from __future__ import annotations

from collections import defaultdict

from .churn import _COMMIT_MARKER, _normalize_path

# A file needs at least this many commits before its ownership ratio is worth
# reporting — one or two commits by one person is not a meaningful "silo".
_MIN_COMMITS_FOR_SILO = 3
# A primary author owning at least this share of a file's commits makes it a
# knowledge-concentration risk worth surfacing.
_SILO_OWNERSHIP_PCT = 80


def _bus_factor(author_commits: dict[str, int], total: int) -> int:
    """Smallest number of top authors whose commits exceed half the total."""
    cumulative = 0
    for rank, commits in enumerate(sorted(author_commits.values(), reverse=True), start=1):
        cumulative += commits
        if cumulative * 2 > total:
            return rank
    return len(author_commits)


def _ownership_reason(primary: str, pct: int, authors: int, bus_factor: int) -> str:
    if bus_factor == 1 and authors == 1:
        return f"只有 {primary} 一个人动过，知识完全集中，离职/请假就没人懂，最该补文档和结对。"
    if bus_factor == 1:
        return (
            f"{primary} 掌握了 {pct}% 的改动，是事实上的 owner，有问题先找 ta，"
            "但也别让知识只压一个人。"
        )
    return (
        f"{authors} 个人共同维护（{primary} 改得最多，占 {pct}%），知识相对分散，改动前可多方对齐。"
    )


def analyze_ownership(
    git_log_text: str | None,
    *,
    scanned_paths: set[str] | list[str] | None = None,
    limit: int = 8,
) -> dict:
    """Parse ``git log --numstat`` text into per-file ownership and silos.

    Args:
        git_log_text: output of :func:`churn.collect_git_log` (``None`` ⇒ empty).
        scanned_paths: if given, only these paths are considered, so ownership
            lines up with the files CodeABC actually scanned.
        limit: how many entries to return in each list.

    Returns ``{"owners", "silos", "commits_analyzed"}``. ``owners`` ranks the
    busiest files by commit count with their primary author; ``silos`` is the
    subset whose knowledge is concentrated in one person (bus factor 1 and a
    dominant owner), sorted so the riskiest (most commits behind one person)
    come first.
    """
    allowed: set[str] | None = set(scanned_paths) if scanned_paths is not None else None

    # path -> author -> number of commits that author made touching the path
    author_commits: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    commits_analyzed = 0

    current_author = ""
    touched: set[str] = set()

    def _flush(files: set[str], author: str) -> None:
        if not files:
            return
        nonlocal commits_analyzed
        commits_analyzed += 1
        for path in files:
            author_commits[path][author] += 1

    for line in (git_log_text or "").splitlines():
        if line.startswith(_COMMIT_MARKER):
            _flush(touched, current_author)
            touched = set()
            parts = line[len(_COMMIT_MARKER) :].split("::")
            current_author = parts[2] if len(parts) >= 3 else ""
            continue
        if not line.strip():
            continue
        cols = line.split("\t")
        if len(cols) != 3:
            continue
        _added, _deleted, raw_path = cols
        path = _normalize_path(raw_path)
        if not path or (allowed is not None and path not in allowed):
            continue
        touched.add(path)
    _flush(touched, current_author)

    owners = []
    for path, commits_by_author in author_commits.items():
        total = sum(commits_by_author.values())
        if total < 2:
            continue
        primary, primary_commits = max(commits_by_author.items(), key=lambda kv: (kv[1], kv[0]))
        pct = round(primary_commits / total * 100)
        authors = len(commits_by_author)
        bus_factor = _bus_factor(commits_by_author, total)
        owners.append(
            {
                "path": path,
                "primary_author": primary,
                "ownership": pct,
                "authors": authors,
                "commits": total,
                "bus_factor": bus_factor,
                "reason": _ownership_reason(primary, pct, authors, bus_factor),
            }
        )

    owners.sort(key=lambda o: (-o["commits"], o["bus_factor"], o["path"]))

    silos = [
        o
        for o in owners
        if o["bus_factor"] == 1
        and o["ownership"] >= _SILO_OWNERSHIP_PCT
        and o["commits"] >= _MIN_COMMITS_FOR_SILO
    ]
    silos.sort(key=lambda o: (-o["commits"], -o["ownership"], o["path"]))

    return {
        "owners": owners[:limit],
        "silos": silos[:limit],
        "commits_analyzed": commits_analyzed,
    }


def render_ownership_markdown(project_name: str, ownership_data: dict | None) -> str:
    """Render the ownership analysis as a Markdown section, or ``""`` if empty.

    Returns an empty string when there's no usable history (e.g. an uploaded,
    non-git project) so callers can skip it cleanly.
    """
    data = ownership_data or {}
    owners = data.get("owners") or []
    silos = data.get("silos") or []
    if not owners:
        return ""

    analyzed = data.get("commits_analyzed", 0)
    lines = [
        f"# {project_name} — 代码归属",
        "",
        f"> 基于最近 {analyzed} 个提交的作者算出，看这块代码该问谁、知识有没有压在一个人身上。",
        "",
        "## 谁在维护（按改动次数）",
        "",
    ]
    lines.extend(
        f"- `{o['path']}` — 主要是 {o['primary_author']}"
        f"（占 {o['ownership']}%、共 {o['authors']} 人、bus factor {o['bus_factor']}）："
        f"{o['reason']}"
        for o in owners
    )
    lines.append("")

    if silos:
        lines.append("## 知识孤岛（只压在一个人身上）")
        lines.append("")
        lines.extend(
            f"- `{s['path']}` — {s['primary_author']} 一个人掌握了 {s['ownership']}%"
            f"（{s['commits']} 次改动）：建议补文档、结对或 code review 分散知识。"
            for s in silos
        )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
