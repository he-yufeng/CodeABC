"""Logic complexity: which files are the hardest to follow.

The import-graph maps say which files are *central*; churn says which change
*often*; this says which carry the most tangled *logic* — the files packed with
branches, loops and nested conditions that a reader has to hold in their head.
For someone learning a codebase, "where is the gnarliest logic" is a different
and useful question from "what's central" or "what changes a lot".

It approximates cyclomatic complexity from the Python AST: every decision point
(an ``if``, ``for``, ``while``, ``except``, a boolean ``and``/``or``, a ternary,
a comprehension filter, a ``match`` case) is one more independent path through
the code, so more of them means more to reason about. ``scan_complexity`` is
pure over the file contents and parses with the standard library, so it needs no
repository; non-Python files and files that don't parse are skipped.
"""

from __future__ import annotations

import ast

# AST node types that introduce an extra branch (one more independent path).
_BRANCH_NODES = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.ExceptHandler,
    ast.With,
    ast.AsyncWith,
    ast.IfExp,  # a ... if cond else b
    ast.Assert,
    ast.comprehension,  # the `for` clause of a comprehension
    ast.match_case,
)


def _file_complexity(tree: ast.AST) -> tuple[int, int]:
    """Return (complexity, function_count) for a parsed module.

    Complexity starts at 1 for the module's straight-line path and gains one for
    each decision point; each boolean operator chain adds one per extra operand
    (``a and b and c`` is two more branches), and each comprehension ``if`` adds
    one too.
    """
    complexity = 1
    functions = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions += 1
            complexity += 1
        elif isinstance(node, _BRANCH_NODES):
            complexity += 1
        elif isinstance(node, ast.BoolOp):
            # `a and b and c` has two operators after the first => two branches.
            complexity += len(node.values) - 1
        elif isinstance(node, ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp):
            # Filters inside the comprehension; the `for` clauses are counted as
            # ast.comprehension above.
            complexity += sum(len(gen.ifs) for gen in node.generators)
    return complexity, functions


def scan_complexity(file_contents: dict[str, str], *, limit: int = 15) -> dict:
    """Rank the project's Python files by approximate logic complexity.

    Args:
        file_contents: mapping of path to file text (as CodeABC already read it).
        limit: how many of the most complex files to return.

    Returns ``{"total", "files"}`` where ``files`` is the most complex Python
    files (descending), each ``{"path", "complexity", "functions", "reason"}``.
    """
    scored: list[dict] = []
    for path, content in file_contents.items():
        if not content or not path.endswith(".py"):
            continue
        try:
            tree = ast.parse(content)
        except (SyntaxError, ValueError):
            continue
        complexity, functions = _file_complexity(tree)
        if complexity <= 1:
            continue  # straight-line file, nothing to flag
        reason = (
            f"约 {complexity} 个判断分支，{functions} 个函数"
            if functions
            else f"约 {complexity} 个判断分支"
        )
        scored.append(
            {"path": path, "complexity": complexity, "functions": functions, "reason": reason}
        )

    scored.sort(key=lambda f: (-f["complexity"], f["path"]))
    return {"total": len(scored), "files": scored[:limit]}


def render_complexity_markdown(project_name: str, data: dict | None) -> str:
    """Render the complexity ranking as Markdown, or ``""`` if none."""
    files = (data or {}).get("files") or []
    if not files:
        return ""

    lines = [
        f"# {project_name} — 逻辑复杂度（最难看懂的文件）",
        "",
        "> 按代码里的判断分支（if/循环/异常/与或/三元等）多少排序——分支越多，"
        "逻辑越绕、越要小心读。这和“被很多文件依赖”“改得勤”是不同的角度。",
        "",
    ]
    lines.extend(f"- `{f['path']}` — {f['reason']}（复杂度 {f['complexity']}）" for f in files)
    return "\n".join(lines).rstrip() + "\n"
