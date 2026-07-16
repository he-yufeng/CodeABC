"""Async surface: which modules run on asyncio, and how much of each is async.

Whether a codebase is async — and which parts — changes how you call into it: an
``async def`` has to be awaited or driven by an event loop, and dropping a
blocking call into an async path is a classic hang. This maps the async surface
so a newcomer sees at a glance whether they are in an asyncio codebase and where
the coroutines live, instead of finding out the first time an ``await`` is
missing.

A module is "async" when it defines at least one ``async def`` (counted anywhere
in the file, including nested helpers, since an inner coroutine still pulls its
caller onto the event loop). :func:`scan_async_surface` is pure over the file
contents (standard-library ``ast``); non-Python, test, and files that don't parse
are skipped.
"""

from __future__ import annotations

import ast


def _is_test_path(path: str) -> bool:
    """Async test helpers are noise for a "how is this project built" map, so tests drop out."""
    lower = path.lower()
    base = lower.rsplit("/", 1)[-1]
    return (
        "/tests/" in lower
        or "/test/" in lower
        or base.startswith("test_")
        or base.endswith("_test.py")
        or base == "conftest.py"
    )


def _count_defs(tree: ast.Module) -> tuple[int, int]:
    """Return (async_defs, sync_defs) for a parsed module, counting nested defs too."""
    async_defs = 0
    sync_defs = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef):
            async_defs += 1
        elif isinstance(node, ast.FunctionDef):
            sync_defs += 1
    return async_defs, sync_defs


def scan_async_surface(file_contents: dict[str, str], *, limit: int = 15) -> dict:
    """Map how much of the project is asynchronous, and where the coroutines live.

    Args:
        file_contents: mapping of path to file text (as CodeABC already read it).
        limit: how many of the most-async files to return.

    Returns ``{"async_functions", "total_functions", "async_modules", "files"}``
    where ``async_modules`` is the count of files that define any coroutine and
    ``files`` are the modules with the most ``async def``s (descending), each
    ``{"path", "async_defs", "sync_defs"}``.
    """
    async_functions = 0
    total_functions = 0
    async_modules = 0
    scored: list[dict] = []

    for path, content in file_contents.items():
        if not content or not path.endswith(".py") or _is_test_path(path):
            continue
        try:
            tree = ast.parse(content)
        except (SyntaxError, ValueError):
            continue

        async_defs, sync_defs = _count_defs(tree)
        total_functions += async_defs + sync_defs
        if async_defs == 0:
            continue

        async_functions += async_defs
        async_modules += 1
        scored.append({"path": path, "async_defs": async_defs, "sync_defs": sync_defs})

    # Most coroutines first, then path for a stable order.
    scored.sort(key=lambda f: (-f["async_defs"], f["path"]))
    return {
        "async_functions": async_functions,
        "total_functions": total_functions,
        "async_modules": async_modules,
        "files": scored[:limit],
    }


def render_async_surface_markdown(project_name: str, data: dict | None) -> str:
    """Render the async-surface map as Markdown, or ``""`` when the project has no coroutines."""
    data = data or {}
    async_functions = data.get("async_functions") or 0
    if not async_functions:
        return ""

    total = data.get("total_functions") or 0
    modules = data.get("async_modules") or 0
    files = data.get("files") or []
    share = round(async_functions / total * 100) if total else 0

    lines = [
        f"# {project_name} — 异步面（哪些模块跑在 asyncio 上）",
        "",
        "> 一个项目是不是异步的、哪些部分是异步的，直接决定你怎么调用它："
        "`async def` 必须被 `await` 或事件循环驱动，往异步路径里塞一个阻塞调用是经典的卡死原因。"
        "这里标出协程都在哪，方便新人一眼看出这是不是个 asyncio 代码库、异步逻辑集中在哪。"
        "（只要文件里有一个 `async def` 就算异步模块，嵌套的协程也计入。）",
        "",
        f"**{async_functions} 个 async 函数**分布在 **{modules} 个模块**里"
        f"（占全部函数的约 {share}%）。",
        "",
    ]
    if files:
        lines.append("异步逻辑最集中的文件：")
        lines.append("")
        for f in files:
            lines.append(
                f"- `{f['path']}` — {f['async_defs']} 个 async 函数"
                f"（另有 {f['sync_defs']} 个同步函数）"
            )
    return "\n".join(lines).rstrip() + "\n"
