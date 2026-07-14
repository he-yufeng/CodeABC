"""API documentation coverage: which public functions and classes have no docstring.

``docs`` measures comment *density* — how many comment/docstring lines a file
carries relative to its code. This asks a different, sharper question: of the
things a reader actually calls — the public functions, classes and methods that
make up a module's surface — how many explain themselves with a docstring?

For someone learning a codebase, an undocumented public API is the wall they hit
first: they can see ``def parse_manifest(path)`` but not what it expects or
returns. This ranks the files whose public surface is least documented, so the
gaps a newcomer will trip over are visible at a glance. It approximates the
``interrogate`` metric from the Python AST: a symbol is "documented" when
``ast.get_docstring`` finds a string, and only public names (no leading
underscore) count, since dunders and private helpers are rarely self-documented
by contract. ``scan_docstring_coverage`` is pure over the file contents and
parses with the standard library, so it needs no repository; non-Python files,
test files, and files that don't parse are skipped.
"""

from __future__ import annotations

import ast

_MISSING_SAMPLE = 5  # how many undocumented symbol names to surface per file


def _is_public(name: str) -> bool:
    """Public API names carry no leading underscore (skips dunders and privates)."""
    return not name.startswith("_")


def _is_test_path(path: str) -> bool:
    """Docstrings on test functions are noise, so tests are left out of the metric."""
    lower = path.lower()
    base = lower.rsplit("/", 1)[-1]
    return (
        "/tests/" in lower
        or "/test/" in lower
        or base.startswith("test_")
        or base.endswith("_test.py")
        or base == "conftest.py"
    )


def _scan_module(tree: ast.Module) -> tuple[int, int, list[str]]:
    """Return (documentable, documented, undocumented_names) for a parsed module.

    Counts public top-level functions and classes plus public methods of public
    classes. Walks only the module and class bodies rather than ``ast.walk`` so
    nested/local helpers — which are not part of the callable surface — are not
    counted.
    """
    documentable = 0
    documented = 0
    missing: list[str] = []

    def _record(has_doc: bool, label: str) -> None:
        nonlocal documentable, documented
        documentable += 1
        if has_doc:
            documented += 1
        else:
            missing.append(label)

    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and _is_public(node.name):
            _record(ast.get_docstring(node) is not None, node.name)
        elif isinstance(node, ast.ClassDef) and _is_public(node.name):
            _record(ast.get_docstring(node) is not None, node.name)
            for sub in node.body:
                if isinstance(sub, ast.FunctionDef | ast.AsyncFunctionDef) and _is_public(sub.name):
                    _record(ast.get_docstring(sub) is not None, f"{node.name}.{sub.name}")

    return documentable, documented, missing


def scan_docstring_coverage(file_contents: dict[str, str], *, limit: int = 15) -> dict:
    """Rank the project's Python files by how much of their public API lacks docstrings.

    Args:
        file_contents: mapping of path to file text (as CodeABC already read it).
        limit: how many of the least-documented files to return.

    Returns ``{"total_symbols", "documented", "coverage", "files"}`` where
    ``coverage`` is the repo-wide documented fraction (0.0-1.0, and 1.0 when there
    is no public API to document) and ``files`` are the files with the most
    undocumented public symbols (descending), each ``{"path", "symbols",
    "documented", "coverage", "missing"}``.
    """
    total_symbols = 0
    total_documented = 0
    scored: list[dict] = []

    for path, content in file_contents.items():
        if not content or not path.endswith(".py") or _is_test_path(path):
            continue
        try:
            tree = ast.parse(content)
        except (SyntaxError, ValueError):
            continue

        documentable, documented, missing = _scan_module(tree)
        if documentable == 0:
            continue  # no public surface to document

        total_symbols += documentable
        total_documented += documented
        if documented >= documentable:
            continue  # fully documented, nothing to flag

        scored.append(
            {
                "path": path,
                "symbols": documentable,
                "documented": documented,
                "coverage": round(documented / documentable, 3),
                "missing": missing[:_MISSING_SAMPLE],
            }
        )

    coverage = round(total_documented / total_symbols, 3) if total_symbols else 1.0
    # Worst first: most undocumented symbols, then lowest coverage, then path.
    scored.sort(key=lambda f: (-(f["symbols"] - f["documented"]), f["coverage"], f["path"]))
    return {
        "total_symbols": total_symbols,
        "documented": total_documented,
        "coverage": coverage,
        "files": scored[:limit],
    }


def render_docstring_coverage_markdown(project_name: str, data: dict | None) -> str:
    """Render the docstring-coverage ranking as Markdown, or ``""`` if nothing to report."""
    data = data or {}
    total = data.get("total_symbols") or 0
    if not total:
        return ""

    coverage_pct = round((data.get("coverage") or 0.0) * 100)
    documented = data.get("documented") or 0
    files = data.get("files") or []

    lines = [
        f"# {project_name} — API 文档覆盖率（哪些公开接口没写文档字符串）",
        "",
        "> 统计每个文件里「别人会调用」的公开函数、类、方法中有多少写了 docstring。"
        "这和「注释密度」不同——密度看整体注释多少，这里只看**对外接口**是否自解释，"
        "没文档的公开接口正是新人最先撞墙的地方。私有成员和 dunder（下划线开头）不计。",
        "",
        f"**整体覆盖率：{coverage_pct}%**（{documented}/{total} 个公开接口有文档字符串）。",
        "",
    ]
    if files:
        lines.append("公开接口文档最缺的文件：")
        lines.append("")
        for f in files:
            missing = "、".join(f["missing"])
            more = "…" if f["symbols"] - f["documented"] > len(f["missing"]) else ""
            lines.append(
                f"- `{f['path']}` — {f['documented']}/{f['symbols']} 有文档"
                f"（{round(f['coverage'] * 100)}%），缺：{missing}{more}"
            )
    return "\n".join(lines).rstrip() + "\n"
