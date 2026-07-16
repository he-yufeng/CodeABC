"""Flag deeply-nested code — functions whose control flow is indented many levels deep.

Deep nesting (an ``if`` inside a ``for`` inside a ``while`` inside a ``try`` ...) is
hard to follow even when each individual branch is simple, so it is a different
signal from :mod:`complexity` (which counts *how many* branches a file has): a
function can have only a few branches yet bury them several levels deep. For a
beginner reading unfamiliar code this is exactly the shape that is hard to hold in
your head, and it points at the functions most worth flattening with early returns,
guard clauses, or an extracted helper.
"""

from __future__ import annotations

import ast

# Control-flow blocks that add a level of indentation.
_NESTING_NODES = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.With,
    ast.AsyncWith,
    ast.Try,
)

# Functions nested this deep or more are surfaced.
_DEPTH_THRESHOLD = 4


def _max_control_depth(node: ast.AST, current: int = 0) -> int:
    """Deepest chain of nested control-flow blocks under ``node``.

    Nested functions and classes are *not* descended into: they are separate
    scopes and are measured on their own pass, so a helper defined inside a
    function does not inflate the outer function's depth.
    """
    best = current
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(child, _NESTING_NODES):
            best = max(best, _max_control_depth(child, current + 1))
        else:
            best = max(best, _max_control_depth(child, current))
    return best


def scan_deep_nesting(
    file_contents: dict[str, str], *, threshold: int = _DEPTH_THRESHOLD, limit: int = 15
) -> dict:
    """Find functions whose control flow nests ``threshold`` levels deep or more.

    Args:
        file_contents: mapping of path to file text (as CodeABC already read it).
        threshold: minimum nesting depth to flag a function.
        limit: how many of the deepest functions to return.

    Returns ``{"total", "max_depth", "threshold", "files"}`` where ``files`` lists
    the deepest functions (descending), each ``{"path", "function", "depth"}``.
    Test files and non-Python files are skipped.
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
                depth = _max_control_depth(node)
                overall_max = max(overall_max, depth)
                if depth >= threshold:
                    flagged.append({"path": path, "function": node.name, "depth": depth})

    flagged.sort(key=lambda f: (-f["depth"], f["path"], f["function"]))
    return {
        "total": len(flagged),
        "max_depth": overall_max,
        "threshold": threshold,
        "files": flagged[:limit],
    }


def render_deep_nesting_markdown(project_name: str, data: dict | None) -> str:
    """Render the deep-nesting section, or an empty string when nothing is flagged."""
    if not data or not data.get("files"):
        return ""

    threshold = data.get("threshold", _DEPTH_THRESHOLD)
    lines = [
        f"## 嵌套过深的函数（{project_name}）",
        "",
        "下面这些函数把 `if / for / while / try` 一层套一层，缩进很深。就算每一层"
        "本身不复杂，层数一多也很难读——你得同时记住「现在在第几层、每一层的条件是"
        f"什么」。这里列出嵌套达到 **{threshold} 层或更深**的函数，它们通常最值得用"
        "「提前 return / 卫语句 / 把里层抽成一个小函数」拍平。",
        "",
        "| 文件 | 函数 | 最深嵌套层数 |",
        "| --- | --- | --- |",
    ]
    for f in data["files"]:
        lines.append(f"| `{f['path']}` | `{f['function']}` | {f['depth']} |")
    return "\n".join(lines)
