"""Project activity pulse: recent commit timeline and contributor rhythm.

When a non-programmer evaluates code they didn't write — outsourced work,
a library they're considering, a fork they inherited — one of the first
questions is "is this actively maintained?". The import graph and test
coverage say nothing about velocity. This module answers that question
from git history: how many commits landed recently, who is active, and
which parts of the codebase are in motion.

Four time windows:
  week      last 7 days
  month     last 30 days
  quarter   last 90 days
  total     all history in the collected log

For each window it reports commit count, unique authors, the files that
changed, and a simple activity label: ``active`` / ``slowing`` /
``stale`` / ``abandoned``.

It reuses the git log text already collected by :func:`churn.collect_git_log`
(format ``::C::hash::timestamp::author``), so no extra shell call is needed.

Pure function over the log text — unit-testable with fixture strings, no
repo required.
"""

from __future__ import annotations

import re
import time

_COMMIT_RE = re.compile(r"::C::([0-9a-f]+)::(\d+)::(.*)")
_NUMSTAT_RE = re.compile(r"^(\d+|-)\t(\d+|-)\t(.+)$")

# Heuristic thresholds for activity labels (commits per 30-day window)
_ACTIVE_THRESHOLD = 5  # ≥5 commits in last month → active
_SLOWING_THRESHOLD = 1  # ≥1 commit in last month but <5 → slowing


def _label(commits_last_30d: int, days_since_last: float) -> str:
    if days_since_last > 365:
        return "abandoned"
    if days_since_last > 90:
        return "stale"
    if commits_last_30d >= _ACTIVE_THRESHOLD:
        return "active"
    if commits_last_30d >= _SLOWING_THRESHOLD:
        return "slowing"
    return "quiet"


_LABEL_ZH = {
    "active": "活跃（近 30 天有 {n} 次提交）",
    "slowing": "减速中（近 30 天仅 {n} 次提交，势头在减弱）",
    "quiet": "平静（近 30 天没有提交，但最近 3 个月内有活动）",
    "stale": "沉寂（超过 3 个月没有新提交）",
    "abandoned": "疑似停摆（超过一年没有新提交）",
}


def _label_zh(label: str, commits_last_30d: int) -> str:
    return _LABEL_ZH.get(label, label).format(n=commits_last_30d)


def analyze_activity(git_log: str | None, *, now: float | None = None) -> dict:
    """Summarise recent project activity from git log text.

    Args:
        git_log: output of ``churn.collect_git_log`` — ``None`` means no git
            history available (uploaded project without .git).
        now: optional Unix timestamp to use as "now" (for testing).

    Returns::

        {
          "available": bool,
          "total_commits": int,
          "first_commit_days_ago": float | None,
          "last_commit_days_ago": float | None,
          "label": str,           # active | slowing | quiet | stale | abandoned
          "label_zh": str,
          "windows": {
            "week":    {"commits": int, "authors": [str, ...], "files": [str, ...]},
            "month":   {...},
            "quarter": {...},
            "total":   {...},
          },
          "top_contributors": [{"author": str, "commits": int}, ...],
          "recently_changed": [str, ...],   # files touched in last 7 days, ranked
          "notes": [str, ...],
        }
    """
    if not git_log:
        return {
            "available": False,
            "total_commits": 0,
            "first_commit_days_ago": None,
            "last_commit_days_ago": None,
            "label": "unknown",
            "label_zh": "无 git 历史（上传的项目无法分析活跃度）",
            "windows": {},
            "top_contributors": [],
            "recently_changed": [],
            "notes": ["上传的项目没有 git 历史，活跃度分析不可用。"],
        }

    ts_now = now if now is not None else time.time()

    # Parse commits
    commits: list[dict] = []
    current: dict | None = None
    for line in git_log.splitlines():
        m = _COMMIT_RE.match(line)
        if m:
            if current:
                commits.append(current)
            current = {
                "hash": m.group(1),
                "ts": int(m.group(2)),
                "author": m.group(3).strip(),
                "files": [],
            }
            continue
        if current is None:
            continue
        nm = _NUMSTAT_RE.match(line)
        if nm:
            fname = nm.group(3).strip()
            # git renames: "old => new" or "{old => new}/suffix"
            if " => " in fname:
                fname = re.sub(r"\{[^}]* => ([^}]*)\}", r"\1", fname).replace(" => ", "/")
            current["files"].append(fname)

    if current:
        commits.append(current)

    if not commits:
        return {
            "available": True,
            "total_commits": 0,
            "first_commit_days_ago": None,
            "last_commit_days_ago": None,
            "label": "unknown",
            "label_zh": "无法解析 git 提交记录",
            "windows": {},
            "top_contributors": [],
            "recently_changed": [],
            "notes": ["git 日志为空或格式无法识别。"],
        }

    # Sort newest → oldest (git log is already newest-first but be safe)
    commits.sort(key=lambda c: c["ts"], reverse=True)
    newest_ts = commits[0]["ts"]
    oldest_ts = commits[-1]["ts"]
    total_commits = len(commits)
    days_since_last = (ts_now - newest_ts) / 86400
    first_commit_days_ago = (ts_now - oldest_ts) / 86400

    # Window boundaries (seconds from now)
    _WINDOWS = {
        "week": 7 * 86400,
        "month": 30 * 86400,
        "quarter": 90 * 86400,
        "total": float("inf"),
    }

    windows: dict[str, dict] = {}
    for name, span in _WINDOWS.items():
        cutoff = ts_now - span
        wc = [c for c in commits if c["ts"] >= cutoff]
        authors: list[str] = []
        files: list[str] = []
        seen_a: set[str] = set()
        seen_f: set[str] = set()
        for c in wc:
            if c["author"] not in seen_a:
                authors.append(c["author"])
                seen_a.add(c["author"])
            for f in c["files"]:
                if f not in seen_f:
                    files.append(f)
                    seen_f.add(f)
        windows[name] = {
            "commits": len(wc),
            "authors": authors[:10],
            "files": files[:15],
        }

    # Top contributors (total history)
    author_counts: dict[str, int] = {}
    for c in commits:
        author_counts[c["author"]] = author_counts.get(c["author"], 0) + 1
    top_contributors = sorted(author_counts.items(), key=lambda x: -x[1])[:8]

    # Recently changed files (last 7 days)
    recently_changed = windows["week"]["files"]

    # Activity label
    commits_last_30d = windows["month"]["commits"]
    label = _label(commits_last_30d, days_since_last)
    label_zh = _label_zh(label, commits_last_30d)

    notes = _build_notes(
        label, commits_last_30d, days_since_last, total_commits, len(author_counts)
    )

    return {
        "available": True,
        "total_commits": total_commits,
        "first_commit_days_ago": round(first_commit_days_ago, 1),
        "last_commit_days_ago": round(days_since_last, 1),
        "label": label,
        "label_zh": label_zh,
        "windows": windows,
        "top_contributors": [{"author": a, "commits": n} for a, n in top_contributors],
        "recently_changed": recently_changed,
        "notes": notes,
    }


def _build_notes(
    label: str,
    commits_last_30d: int,
    days_since_last: float,
    total_commits: int,
    unique_authors: int,
) -> list[str]:
    notes = []
    if label == "active":
        notes.append(
            f"项目处于活跃维护期，近 30 天有 {commits_last_30d} 次提交，是一个健康的节奏。"
        )
    elif label == "slowing":
        notes.append(
            f"近 30 天提交减少到 {commits_last_30d} 次，势头在放缓；"
            "如依赖此项目需关注它的维护节奏。"
        )
    elif label == "quiet":
        notes.append(
            f"近 30 天没有新提交，但最近 3 个月内有活动，"
            f"距上次提交约 {round(days_since_last)} 天。可能正处于稳定期或低活跃阶段。"
        )
    elif label == "stale":
        notes.append(
            f"已超过 3 个月没有新提交（距上次提交 {round(days_since_last)} 天），"
            "项目可能处于停更或维护模式，使用前请确认依赖的稳定性。"
        )
    elif label == "abandoned":
        notes.append(
            f"超过一年没有提交（距上次提交约 {round(days_since_last / 30)} 个月），"
            "项目可能已停止维护，建议寻找活跃的替代方案或做好长期自维护的准备。"
        )
    if unique_authors == 1:
        notes.append("这是单人项目，整个提交历史由一位作者贡献，对外部依赖方来说存在单点风险。")
    elif unique_authors <= 3:
        notes.append(f"小型团队项目，共 {unique_authors} 位贡献者参与了提交历史。")
    else:
        notes.append(f"共 {unique_authors} 位贡献者参与过提交，社区基础相对健康。")
    if total_commits < 20:
        notes.append(f"总提交数较少（{total_commits} 次），项目可能较新或提交历史较短。")
    return notes


def render_activity_markdown(project_name: str, data: dict | None) -> str:
    """Render the activity summary as a Markdown section, or ``""`` if unavailable."""
    if not data or not data.get("available"):
        return ""
    label_zh = data.get("label_zh", "")
    lines = [
        f"# 活跃度脉冲（{project_name}）",
        "",
        f"> 状态：**{label_zh}**",
        "",
    ]
    for note in data.get("notes", []):
        lines.append(f"- {note}")

    # Window summary table
    windows = data.get("windows", {})
    if windows:
        lines.append("")
        lines.append("## 提交节奏")
        lines.append("")
        lines.append("| 时间窗口 | 提交次数 | 活跃作者 |")
        lines.append("|----------|----------|----------|")
        _WIN_LABELS = {
            "week": "近 7 天",
            "month": "近 30 天",
            "quarter": "近 90 天",
            "total": "全部历史",
        }
        for key in ("week", "month", "quarter", "total"):
            w = windows.get(key, {})
            label = _WIN_LABELS.get(key, key)
            lines.append(f"| {label} | {w.get('commits', 0)} | {len(w.get('authors', []))} |")

    top = data.get("top_contributors", [])
    if top:
        lines.append("")
        lines.append("## 主要贡献者")
        lines.append("")
        for t in top[:5]:
            lines.append(f"- {t['author']}（{t['commits']} 次提交）")

    recent = data.get("recently_changed", [])
    if recent:
        lines.append("")
        lines.append("## 近 7 天改动的文件")
        lines.append("")
        for f in recent[:10]:
            lines.append(f"- `{f}`")

    return "\n".join(lines).rstrip() + "\n"
