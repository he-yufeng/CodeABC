"""Flag over-long functions — functions whose body runs on for many lines.

Length is a readability signal that :mod:`complexity` and :mod:`deep_nesting` both
miss. A function can have very few branches (low cyclomatic complexity) and shallow
nesting, yet still be hundreds of lines of straight-line code — reading it means
scrolling and holding a long story in your head with no natural place to pause. For
a beginner these are the functions that feel exhausting even though no single line
is hard, and they are usually the clearest candidates for splitting into a few
named helper functions, each doing one thing.

This is deliberately a *physical line span* (``def`` line through the last line of
the body), which is the same yardstick common linters use, rather than a token or
statement count: it is the number a reader actually scrolls past, and it needs no
language-specific tuning to be meaningful to a newcomer.
"""

from __future__ import annotations

import ast

# Functions at least this many lines long are surfaced.
_LENGTH_THRESHOLD = 60


def _function_length(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Line span of a function, from its ``def`` line through the end of its body.

    Decorators are excluded (``node.lineno`` points at ``def``, not at the first
    decorator), so a function is not penalised for the decorators stacked above it.
    Falls back to a single line when ``end_lineno`` is unavailable.
    """
    end = getattr(node, "end_lineno", None)
    if end is None:
        return 1
    return end - node.lineno + 1


def scan_long_functions(
    file_contents: dict[str, str], *, threshold: int = _LENGTH_THRESHOLD, limit: int = 15
) -> dict:
    """Find functions whose body spans ``threshold`` lines or more.

    Args:
        file_contents: mapping of path to file text (as CodeABC already read it).
        threshold: minimum line span to flag a function.
        limit: how many of the longest functions to return.

    Returns ``{"total", "max_length", "threshold", "files"}`` where ``files`` lists
    the longest functions (descending), each ``{"path", "function", "length"}``.
    Test files and non-Python files are skipped. A nested helper is measured on its
    own, so both an over-long outer function and an over-long inner one can surface.
    """
    flagged: list[dict] = []
    overall_max = 0
    for path, content in file_contents.items():
        if not content or not path.endswith(".py"):
            continue
        base = path.rsplit("/", 1)[-1]
        if base.startswith("test_") or base.endswith("_test.py") or "/tests/" in path:
            continue
        try:
            tree = ast.parse(content)
        except (SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                length = _function_length(node)
                overall_max = max(overall_max, length)
                if length >= threshold:
                    flagged.append({"path": path, "function": node.name, "length": length})

    flagged.sort(key=lambda f: (-f["length"], f["path"], f["function"]))
    return {
        "total": len(flagged),
        "max_length": overall_max,
        "threshold": threshold,
        "files": flagged[:limit],
    }


def render_long_functions_markdown(project_name: str, data: dict | None) -> str:
    """Render the long-functions section, or an empty string when nothing is flagged."""
    if not data or not data.get("files"):
        return ""

    threshold = data.get("threshold", _LENGTH_THRESHOLD)
    lines = [
        f"## 过长的函数（{project_name}）",
        "",
        "下面这些函数一口气写了很多行。哪怕里面没有复杂的分支、也没有很深的嵌套，"
        "光是「长」本身就难读——你得一直往下滚，脑子里还要记着开头发生了什么，中间"
        f"却没有一个自然的停顿点。这里列出**{threshold} 行或更长**的函数，它们通常"
        "最值得拆成几个各司其职、名字取好的小函数：一个函数只做一件事，读的人就能"
        "一段一段看懂，而不用一次消化一整篇。",
        "",
        "| 文件 | 函数 | 行数 |",
        "| --- | --- | --- |",
    ]
    for f in data["files"]:
        lines.append(f"| `{f['path']}` | `{f['function']}` | {f['length']} |")
    return "\n".join(lines)
