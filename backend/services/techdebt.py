"""Tech-debt markers: surface the codebase's own TODO/FIXME notes.

A codebase usually documents its own rough edges inline — ``TODO`` for things
left unfinished, ``FIXME`` for known-broken spots, ``HACK`` for deliberate
shortcuts, ``XXX`` for "look here, this is suspicious". Collecting them gives a
newcomer a fast, honest map of where the authors themselves flagged debt,
without having to read every file.

This is a *self-declared* signal (what the authors wrote down), complementary to
the churn/ownership history and the static import graph. :func:`scan_tech_debt`
is pure — it operates on the already-read file contents, so it is unit-testable
with plain strings and needs no repository.

Markers are matched as whole, upper-case words (the near-universal convention),
which keeps prose like "todo list" or "debugging" from being mistaken for a
marker.
"""

from __future__ import annotations

import re
from collections import Counter

# Whole-word, upper-case markers only. Leading comment punctuation and the
# usual separators after the marker are dropped so the captured note is clean.
_MARKER_RE = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b[:\s)\-]*(.*)")

# A note longer than this is almost certainly a run-on line; keep the map terse.
_MAX_NOTE_LEN = 160


def _kind_reason(kind: str, count: int) -> str:
    if kind == "FIXME":
        return f"{count} 处 FIXME：作者标了“这里是坏的/要修”，读到相关代码时别当它是对的。"
    if kind == "HACK":
        return f"{count} 处 HACK：作者承认是临时绕过/取巧，改动前先确认有没有更干净的做法。"
    if kind == "XXX":
        return f"{count} 处 XXX：作者标了“可疑、看这里”，往往藏着隐患或待定决策。"
    return f"{count} 处 TODO：作者留的未完成事项，是了解“还差什么”的最快线索。"


def scan_tech_debt(
    file_contents: dict[str, str],
    *,
    limit: int = 15,
    per_file_limit: int = 5,
) -> dict:
    """Collect ``TODO``/``FIXME``/``HACK``/``XXX`` markers from file contents.

    Args:
        file_contents: mapping of path to file text (as CodeABC already read it).
        limit: how many files to return in the ranked list.
        per_file_limit: how many individual markers to keep per file.

    Returns ``{"total", "by_kind", "files"}`` where ``files`` is ranked by how
    many markers each file carries (most first), and ``by_kind`` counts each
    marker type across the whole project.
    """
    by_file: dict[str, list[dict]] = {}
    kind_counts: Counter[str] = Counter()
    total = 0

    for path, content in file_contents.items():
        if not content:
            continue
        for line_no, line in enumerate(content.splitlines(), start=1):
            match = _MARKER_RE.search(line)
            if not match:
                continue
            kind = match.group(1)
            note = match.group(2).strip()[:_MAX_NOTE_LEN]
            by_file.setdefault(path, []).append({"line": line_no, "kind": kind, "note": note})
            kind_counts[kind] += 1
            total += 1

    files = [
        {"path": path, "count": len(markers), "markers": markers[:per_file_limit]}
        for path, markers in by_file.items()
    ]
    files.sort(key=lambda f: (-f["count"], f["path"]))

    return {
        "total": total,
        "by_kind": dict(kind_counts),
        "files": files[:limit],
    }


def render_techdebt_markdown(project_name: str, techdebt_data: dict | None) -> str:
    """Render the tech-debt markers as a Markdown section, or ``""`` if none."""
    data = techdebt_data or {}
    files = data.get("files") or []
    if not files:
        return ""

    total = data.get("total", 0)
    by_kind = data.get("by_kind") or {}
    lines = [
        f"# {project_name} — 待办与技术债",
        "",
        f"> 扫描代码里作者自己留的 TODO / FIXME / HACK / XXX 标记，共 {total} 处，"
        "是了解“作者知道哪里还没做好”的最快线索。",
        "",
    ]

    if by_kind:
        lines.append("## 按类型")
        lines.append("")
        for kind in ("FIXME", "HACK", "XXX", "TODO"):
            count = by_kind.get(kind)
            if count:
                lines.append(f"- {_kind_reason(kind, count)}")
        lines.append("")

    lines.append("## 标记最多的文件")
    lines.append("")
    for entry in files:
        lines.append(f"- `{entry['path']}` — {entry['count']} 处")
        for marker in entry["markers"]:
            note = f"：{marker['note']}" if marker["note"] else ""
            lines.append(f"  - L{marker['line']} `{marker['kind']}`{note}")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"
