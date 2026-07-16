"""Type-annotation coverage: which public functions leave their types unstated.

``docstrings`` asks whether a module's public surface *explains* itself; this
asks whether it *types* itself. A function is "typed" when it declares a return
annotation and every parameter (other than a leading ``self``/``cls``) carries
one — the same bar mypy's ``disallow-untyped-defs`` enforces. Fully typed code
says what goes in and what comes out without being run, and it is the difference
between an editor that can autocomplete and catch mistakes and one that guesses.

For someone modifying an unfamiliar codebase, an un-typed public function is a
quiet trap: ``def merge(a, b)`` gives no hint whether ``a`` is a dict, a path, or
a dataframe. This ranks the files whose public API is least annotated so the
riskiest places to change surface at a glance. ``scan_typing_coverage`` is pure
over the file contents and parses with the standard library, so it needs no
repository; non-Python files, test files, and files that don't parse are skipped.
"""

from __future__ import annotations

import ast

_MISSING_SAMPLE = 5  # how many un-typed symbol names to surface per file


def _is_public(name: str) -> bool:
    """Public API names carry no leading underscore (skips dunders and privates)."""
    return not name.startswith("_")


def _is_test_path(path: str) -> bool:
    """Type hints on test functions are noise, so tests are left out of the metric."""
    lower = path.lower()
    base = lower.rsplit("/", 1)[-1]
    return (
        "/tests/" in lower
        or "/test/" in lower
        or base.startswith("test_")
        or base.endswith("_test.py")
        or base == "conftest.py"
    )


def _is_typed(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """True when the function declares a return type and every parameter is annotated.

    A leading ``self``/``cls`` is exempt (methods conventionally leave it bare),
    as are the ``*args``/``**kwargs`` only when the codebase omits them; both the
    variadic forms are required to be annotated when present. This matches mypy's
    ``disallow-untyped-defs`` "typed def" bar.
    """
    if node.returns is None:
        return False
    args = node.args
    positional = [*args.posonlyargs, *args.args]
    if positional and positional[0].arg in ("self", "cls"):
        positional = positional[1:]
    for arg in (*positional, *args.kwonlyargs):
        if arg.annotation is None:
            return False
    if args.vararg is not None and args.vararg.annotation is None:
        return False
    if args.kwarg is not None and args.kwarg.annotation is None:
        return False
    return True


def _scan_module(tree: ast.Module) -> tuple[int, int, list[str]]:
    """Return (typeable, typed, untyped_names) for a parsed module.

    Counts public top-level functions plus public methods of public classes. A
    class itself has no call signature to annotate, so only its methods count.
    Walks the module and class bodies rather than ``ast.walk`` so nested/local
    helpers — which are not part of the callable surface — are left out.
    """
    typeable = 0
    typed = 0
    missing: list[str] = []

    def _record(is_typed: bool, label: str) -> None:
        nonlocal typeable, typed
        typeable += 1
        if is_typed:
            typed += 1
        else:
            missing.append(label)

    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and _is_public(node.name):
            _record(_is_typed(node), node.name)
        elif isinstance(node, ast.ClassDef) and _is_public(node.name):
            for sub in node.body:
                if isinstance(sub, ast.FunctionDef | ast.AsyncFunctionDef) and _is_public(sub.name):
                    _record(_is_typed(sub), f"{node.name}.{sub.name}")

    return typeable, typed, missing


def scan_typing_coverage(file_contents: dict[str, str], *, limit: int = 15) -> dict:
    """Rank the project's Python files by how much of their public API lacks type hints.

    Args:
        file_contents: mapping of path to file text (as CodeABC already read it).
        limit: how many of the least-annotated files to return.

    Returns ``{"total_symbols", "typed", "coverage", "files"}`` where ``coverage``
    is the repo-wide typed fraction (0.0-1.0, and 1.0 when there is no public API
    to type) and ``files`` are the files with the most un-typed public functions
    (descending), each ``{"path", "symbols", "typed", "coverage", "missing"}``.
    """
    total_symbols = 0
    total_typed = 0
    scored: list[dict] = []

    for path, content in file_contents.items():
        if not content or not path.endswith(".py") or _is_test_path(path):
            continue
        try:
            tree = ast.parse(content)
        except (SyntaxError, ValueError):
            continue

        typeable, typed, missing = _scan_module(tree)
        if typeable == 0:
            continue  # no public functions to type

        total_symbols += typeable
        total_typed += typed
        if typed >= typeable:
            continue  # fully typed, nothing to flag

        scored.append(
            {
                "path": path,
                "symbols": typeable,
                "typed": typed,
                "coverage": round(typed / typeable, 3),
                "missing": missing[:_MISSING_SAMPLE],
            }
        )

    coverage = round(total_typed / total_symbols, 3) if total_symbols else 1.0
    # Worst first: most un-typed functions, then lowest coverage, then path.
    scored.sort(key=lambda f: (-(f["symbols"] - f["typed"]), f["coverage"], f["path"]))
    return {
        "total_symbols": total_symbols,
        "typed": total_typed,
        "coverage": coverage,
        "files": scored[:limit],
    }


def render_typing_coverage_markdown(project_name: str, data: dict | None) -> str:
    """Render the type-annotation coverage ranking as Markdown, or ``""`` if nothing to report."""
    data = data or {}
    total = data.get("total_symbols") or 0
    if not total:
        return ""

    coverage_pct = round((data.get("coverage") or 0.0) * 100)
    typed = data.get("typed") or 0
    files = data.get("files") or []

    lines = [
        f"# {project_name} — 类型注解覆盖率（哪些公开函数没写全类型标注）",
        "",
        "> 统计每个文件里「别人会调用」的公开函数、方法中有多少写全了类型标注"
        "（参数和返回值都标了）。写全类型的代码不用运行就能看出「传什么、返回什么」，"
        "编辑器也能自动补全并提前报错；没标类型的公开函数正是改起来最容易踩坑的地方。"
        "开头的 `self`/`cls` 不计，私有成员和 dunder（下划线开头）也不计。",
        "",
        f"**整体覆盖率：{coverage_pct}%**（{typed}/{total} 个公开函数写全了类型标注）。",
        "",
    ]
    if files:
        lines.append("类型标注最缺的文件：")
        lines.append("")
        for f in files:
            missing = "、".join(f["missing"])
            more = "…" if f["symbols"] - f["typed"] > len(f["missing"]) else ""
            lines.append(
                f"- `{f['path']}` — {f['typed']}/{f['symbols']} 标了类型"
                f"（{round(f['coverage'] * 100)}%），缺：{missing}{more}"
            )
    return "\n".join(lines).rstrip() + "\n"
