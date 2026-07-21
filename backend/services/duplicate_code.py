"""Flag duplicated code blocks — the same code copied into more than one place.

Copy-paste is the quietest way a codebase rots. The first copy is fine; the
problem shows up three months later, when someone fixes a bug in one copy and
the others keep the old behavior. Nothing warns about that — the copies don't
know about each other, and they drift apart one silent edit at a time. For a
beginner this is also the easiest maintenance trap to understand: "the same
thing written twice means every change has to happen twice."

None of the other readability analyzers catch this: a copied block can be
short, shallow, low-complexity, and have few parameters. Duplication is its own
axis.

The detection is deliberately simple and honest: normalize each file's lines
(drop blanks, comments, and imports, collapse whitespace), hash every window
of a few consecutive lines, and report windows that show up in more than one
file, or three or more times in one file. Exact-duplicate only — fuzzy
"similar" matching belongs to a much bigger tool, and guessing wrong there
costs more trust than it earns.
"""

from __future__ import annotations

import hashlib
import re

# Consecutive lines a window must span to count as a block.
_WINDOW = 6
# Same-file copies needed to flag (cross-file only needs two).
_SAME_FILE_MIN = 3

_BLANK_RE = re.compile(r"^\s*$")
_COMMENT_RE = re.compile(r"^\s*#")
_IMPORT_RE = re.compile(r"^\s*(import\s|from\s)")
_WS_RE = re.compile(r"\s+")


def _normalized_lines(content: str) -> list[tuple[int, str]]:
    """Return (line number, normalized text) pairs, skipping noise lines."""
    out: list[tuple[int, str]] = []
    for lineno, raw in enumerate(content.splitlines(), 1):
        if _BLANK_RE.match(raw) or _COMMENT_RE.match(raw) or _IMPORT_RE.match(raw):
            continue
        out.append((lineno, _WS_RE.sub(" ", raw.strip())))
    return out


def _is_test(path: str) -> bool:
    base = path.rsplit("/", 1)[-1]
    return base.startswith("test_") or base.endswith("_test.py") or "/tests/" in path


def _merge_overlapping(clusters: list[list[dict]], window: int) -> list[list[dict]]:
    """Union clusters whose occurrences sit in the same file within ``window``
    lines — those are sliding windows of one physical copy, not two copies."""
    parent = list(range(len(clusters)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(len(clusters)):
        for j in range(i + 1, len(clusters)):
            if any(
                oa["path"] == ob["path"] and abs(oa["line"] - ob["line"]) < window
                for oa in clusters[i]
                for ob in clusters[j]
            ):
                union(i, j)

    merged: dict[int, list[dict]] = {}
    for idx, occurrences in enumerate(clusters):
        merged.setdefault(find(idx), [])
        merged[find(idx)].extend(occurrences)
    return list(merged.values())


def _collapse_window_ghosts(occurrences: list[dict], window: int) -> list[dict]:
    """Keep one occurrence per physical copy: within a file, windows starting
    less than ``window`` lines apart are the same copy seen twice."""
    kept: list[dict] = []
    for o in sorted(occurrences, key=lambda o: (o["path"], o["line"])):
        if kept and kept[-1]["path"] == o["path"] and o["line"] - kept[-1]["line"] < window:
            continue
        kept.append(o)
    return kept


def scan_duplicate_code(
    file_contents: dict[str, str], *, window: int = _WINDOW, limit: int = 10
) -> dict:
    """Find line windows that appear in more than one place.

    Args:
        file_contents: mapping of path to file text (as CodeABC already read it).
        window: consecutive normalized lines that make up one block.
        limit: how many clusters to return.

    Returns ``{"total", "total_occurrences", "window", "clusters"}`` where each
    cluster is a list of ``{"path", "line"}`` occurrences (one per physical
    copy, sorted). A block counts when it appears in two different files, or
    at least three times in one file. Test files and non-Python files are
    skipped.
    """
    blocks: dict[str, list[dict]] = {}
    for path, content in file_contents.items():
        if not content or not path.endswith(".py") or _is_test(path):
            continue
        lines = _normalized_lines(content)
        for i in range(len(lines) - window + 1):
            window_text = "\n".join(text for _, text in lines[i : i + window])
            digest = hashlib.sha1(window_text.encode()).hexdigest()[:16]
            occurrence = {"path": path, "line": lines[i][0]}
            bucket = blocks.setdefault(digest, [])
            if occurrence not in bucket:
                bucket.append(occurrence)

    clusters = []
    # singleton windows can never be duplicates; only multi-occurrence digests
    # are candidates, and spatial merging happens within that set so unique
    # neighboring windows don't get absorbed into a real cluster
    candidates = [occurrences for occurrences in blocks.values() if len(occurrences) >= 2]
    for occurrences in _merge_overlapping(candidates, window):
        copies = _collapse_window_ghosts(occurrences, window)
        paths = {o["path"] for o in copies}
        if len(paths) >= 2 or len(copies) >= _SAME_FILE_MIN:
            clusters.append(sorted(copies, key=lambda o: (o["path"], o["line"])))
    clusters.sort(key=lambda c: (-len(c), c[0]["path"], c[0]["line"]))

    return {
        "total": len(clusters),
        "total_occurrences": sum(len(c) for c in clusters),
        "window": window,
        "clusters": clusters[:limit],
    }


def render_duplicate_code_markdown(project_name: str, data: dict | None) -> str:
    """Render the duplicated-code section, or an empty string when none is found."""
    if not data or not data.get("clusters"):
        return ""

    window = data.get("window", _WINDOW)
    lines = [
        f"## 重复的代码（{project_name}）",
        "",
        "下面这些代码块在不止一个地方出现，长得几乎一模一样（连续 "
        f"{window} 行以上）。复制的时候省事，麻烦在后面：哪天改其中一处，"
        "其余几处不会跟着变，bug 就这样一个版本一个版本地留下来。建议把它们"
        "抽成一个公共函数，以后只改一处：",
        "",
        "| 出现位置 |",
        "| --- |",
    ]
    for cluster in data["clusters"]:
        spots = "<br>".join(f"`{o['path']}` 第 {o['line']} 行" for o in cluster)
        lines.append(f"| {spots} |")
    return "\n".join(lines)
