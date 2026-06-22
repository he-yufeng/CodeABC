"""Documentation coverage: which source files are written down, and which aren't.

Tests answer "is this code verified?"; this answers the sibling question a
non-programmer asks when inheriting a codebase: "is this code *explained*?".
A large source file with almost no comments or docstrings is the hardest to
read and the riskiest to change blind — and it's exactly the kind of thing that
doesn't show up in a test-coverage or churn report.

:func:`assess_doc_coverage` walks the already-read file contents, counts code
lines vs. comment/docstring lines per source file, and flags the ones that
carry real logic yet are effectively undocumented. The bigger a bare file is,
the higher it ranks: a 300-line module with no comments hurts more than a
10-line helper.

Pure functions over the file-content map — no repo or git history needed, so it
is unit-testable with plain strings. The comment detection is a deterministic
heuristic (line-comment prefixes, C-style block comments, Python docstrings),
not a full parser; it aims to be honest about density, not byte-perfect.
"""

from __future__ import annotations

# Extension -> (line-comment prefix, has C-style /* */ blocks).
# Python is handled specially because triple-quoted docstrings count as docs.
_LINE_COMMENT: dict[str, str] = {
    "py": "#",
    "pyi": "#",
    "js": "//",
    "jsx": "//",
    "ts": "//",
    "tsx": "//",
    "go": "//",
    "java": "//",
    "rs": "//",
    "c": "//",
    "h": "//",
    "cpp": "//",
    "hpp": "//",
    "cc": "//",
    "cs": "//",
    "kt": "//",
    "swift": "//",
    "scala": "//",
}
_C_STYLE = {
    "js",
    "jsx",
    "ts",
    "tsx",
    "go",
    "java",
    "rs",
    "c",
    "h",
    "cpp",
    "hpp",
    "cc",
    "cs",
    "kt",
    "swift",
    "scala",
}
_PY = {"py", "pyi"}

# A file needs at least this many code lines before "no docs" is worth flagging;
# tiny files don't need a comment to be understood.
_MIN_CODE_LINES = 15
# At or below this comment-to-code ratio a file counts as "under-documented".
_UNDER_DOCUMENTED_RATIO = 0.05

_TEST_SEGMENTS = {"test", "tests", "__tests__", "spec", "specs"}
_SKIP_NAMES = {"__init__.py", "conftest.py", "setup.py"}


def _ext(path: str) -> str:
    name = path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def _is_test_or_skip(path: str) -> bool:
    norm = path.replace("\\", "/")
    segments = [s for s in norm.split("/") if s]
    if any(s in _TEST_SEGMENTS for s in segments):
        return True
    name = segments[-1] if segments else ""
    if name in _SKIP_NAMES:
        return True
    stem = name.rsplit(".", 1)[0] if "." in name else name
    # test_x.py / x_test.go / x.test.ts / x.spec.ts naming conventions
    return stem.startswith("test_") or stem.endswith("_test") or ".test" in name or ".spec" in name


def _count_lines(content: str, ext: str) -> tuple[int, int]:
    """Return (code_lines, comment_lines) for one source file."""
    line_token = _LINE_COMMENT.get(ext, "")
    c_style = ext in _C_STYLE
    py = ext in _PY

    code = 0
    comment = 0
    in_block = False  # C-style /* */
    in_doc = False  # Python triple-quote docstring
    doc_delim = ""

    for raw in content.splitlines():
        line = raw.strip()
        if not line:
            continue

        if in_block:
            comment += 1
            if "*/" in line:
                in_block = False
            continue

        if in_doc:
            comment += 1
            if doc_delim in line:
                in_doc = False
            continue

        # Python docstring / triple-quoted block.
        if py and (line.startswith('"""') or line.startswith("'''")):
            doc_delim = line[:3]
            comment += 1
            # A one-line """doc""" opens and closes on the same line.
            if line.count(doc_delim) < 2:
                in_doc = True
            continue

        # C-style block comment start.
        if c_style and line.startswith("/*"):
            comment += 1
            if "*/" not in line:
                in_block = True
            continue

        # Whole-line // or # comment.
        if line_token and line.startswith(line_token):
            comment += 1
            continue

        code += 1

    return code, comment


def _reason(code: int, ratio: int) -> str:
    if ratio == 0:
        return f"{code} 行代码、几乎没有注释或文档，读懂全靠猜，改动前最该补一句说明它在做什么。"
    return f"{code} 行代码只有约 {ratio}% 的注释/文档，核心逻辑缺解释，新人上手成本高。"


def assess_doc_coverage(file_contents: dict[str, str], *, limit: int = 12) -> dict:
    """Assess documentation density across source files.

    Args:
        file_contents: mapping of path to file text (as CodeABC already read it).
        limit: how many under-documented files to return in the ranked list.

    Returns::

        {
          "total_source_files": int,
          "documented_files": int,
          "undocumented_files": int,
          "doc_percent": int,           # 0-100, documented / total source files
          "under_documented": [         # ranked by code size (biggest first)
            {"path", "code_lines", "comment_lines", "ratio", "reason"}, ...
          ],
          "notes": [str, ...],
        }
    """
    total = 0
    documented = 0
    under: list[dict] = []

    for path, content in file_contents.items():
        if not content:
            continue
        ext = _ext(path)
        if ext not in _LINE_COMMENT or _is_test_or_skip(path):
            continue

        code, comment = _count_lines(content, ext)
        if code == 0:
            continue
        total += 1
        ratio = comment / (code + comment) if (code + comment) else 0.0
        if ratio > _UNDER_DOCUMENTED_RATIO:
            documented += 1
        if code >= _MIN_CODE_LINES and ratio <= _UNDER_DOCUMENTED_RATIO:
            pct = int(round(ratio * 100))
            under.append(
                {
                    "path": path,
                    "code_lines": code,
                    "comment_lines": comment,
                    "ratio": pct,
                    "reason": _reason(code, pct),
                }
            )

    under.sort(key=lambda f: (-f["code_lines"], f["path"]))
    undocumented = total - documented
    doc_percent = int(round(documented / total * 100)) if total else 0

    notes: list[str] = []
    if total == 0:
        notes.append("没有发现可统计的源代码文件。")
    elif not under:
        notes.append("核心源文件都带了一定注释/文档，文档基线不错。")

    return {
        "total_source_files": total,
        "documented_files": documented,
        "undocumented_files": undocumented,
        "doc_percent": doc_percent,
        "under_documented": under[:limit],
        "notes": notes,
    }


def render_doc_coverage_markdown(project_name: str, data: dict | None) -> str:
    """Render the documentation-coverage map as a Markdown section, or ``""``."""
    d = data or {}
    total = d.get("total_source_files", 0)
    if not total:
        return ""

    lines = [
        f"# {project_name} — 文档覆盖",
        "",
        f"> {total} 个源文件里约 {d.get('doc_percent', 0)}% 带有注释/文档。"
        "下面这些是「代码不少、却几乎没解释」的文件，对刚接手的人最难读、改起来最容易踩坑。",
        "",
    ]

    under = d.get("under_documented") or []
    if not under:
        lines.append("核心源文件都带了一定注释，没有明显「裸奔」的大文件。")
        return "\n".join(lines).rstrip() + "\n"

    lines.append("## 最该补文档的文件")
    lines.append("")
    for entry in under:
        lines.append(f"- `{entry['path']}` — {entry['reason']}")

    notes = d.get("notes") or []
    if notes:
        lines += ["", "## 注意事项", ""]
        for n in notes:
            lines.append(f"- {n}")

    return "\n".join(lines).rstrip() + "\n"
