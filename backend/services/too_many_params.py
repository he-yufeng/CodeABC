"""Flag functions that take too many parameters.

A long parameter list is a readability and design signal that is orthogonal to
:mod:`complexity` (branch count), :mod:`deep_nesting` (indentation depth), and
:mod:`long_functions` (line span): a short, flat function can still be painful to
call and read if it asks for eight separate arguments. The caller has to remember
what each positional slot means and keep the order straight, and the reader has to
hold the whole list in mind to understand what the function needs. These are the
functions most worth refactoring by grouping related arguments into an object (or
dataclass), or by splitting the work into smaller, single-purpose helpers.

A leading ``self`` / ``cls`` receiver is not counted, and ``*args`` / ``**kwargs``
are ignored on purpose: they collapse a variable number of arguments rather than
adding named ones, so they do not carry the same "remember every slot" cost.
"""

from __future__ import annotations

import ast

# Functions with at least this many named parameters are surfaced.
_PARAM_THRESHOLD = 6


def _param_count(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Number of named parameters, excluding a ``self`` / ``cls`` receiver.

    Positional-only, regular, and keyword-only parameters are all counted;
    ``*args`` / ``**kwargs`` are not, since they aggregate arguments rather than
    naming individual ones.
    """
    args = node.args
    count = len(args.posonlyargs) + len(args.args) + len(args.kwonlyargs)
    leading = args.posonlyargs or args.args
    if leading and leading[0].arg in ("self", "cls"):
        count -= 1
    return count


def scan_too_many_params(
    file_contents: dict[str, str], *, threshold: int = _PARAM_THRESHOLD, limit: int = 15
) -> dict:
    """Find functions that declare ``threshold`` named parameters or more.

    Args:
        file_contents: mapping of path to file text (as CodeABC already read it).
        threshold: minimum named-parameter count to flag a function.
        limit: how many of the widest functions to return.

    Returns ``{"total", "max_params", "threshold", "files"}`` where ``files`` lists
    the widest functions (descending), each ``{"path", "function", "params"}``.
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
                params = _param_count(node)
                overall_max = max(overall_max, params)
                if params >= threshold:
                    flagged.append({"path": path, "function": node.name, "params": params})

    flagged.sort(key=lambda f: (-f["params"], f["path"], f["function"]))
    return {
        "total": len(flagged),
        "max_params": overall_max,
        "threshold": threshold,
        "files": flagged[:limit],
    }


def render_too_many_params_markdown(project_name: str, data: dict | None) -> str:
    """Render the too-many-parameters section, or an empty string when nothing is flagged."""
    if not data or not data.get("files"):
        return ""

    threshold = data.get("threshold", _PARAM_THRESHOLD)
    lines = [
        f"## 参数过多的函数（{project_name}）",
        "",
        "下面这些函数一次要接收很多个参数。参数一多，调用它的时候就得记住每个位置该"
        "传什么、顺序还不能错，很容易传错或漏传；读代码的人也要同时盯着一长串参数才"
        f"能明白这个函数到底需要什么。这里列出参数达到 **{threshold} 个或更多**的函数，"
        "它们通常值得把关系紧密的几个参数打包成一个对象（或 dataclass）一起传，或者"
        "干脆拆成职责更单一的小函数。",
        "",
        "| 文件 | 函数 | 参数个数 |",
        "| --- | --- | --- |",
    ]
    for f in data["files"]:
        lines.append(f"| `{f['path']}` | `{f['function']}` | {f['params']} |")
    return "\n".join(lines)
