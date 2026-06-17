"""Build a lightweight import graph and rank the most depended-on files.

Fan-in (how many other files import a given file) is a cheap, deterministic
proxy for where a project's load-bearing logic lives: utilities, models and core
services tend to be imported everywhere, while glue and leaf scripts are not. We
surface the top files next to the reading map so a newcomer knows where to start,
without spending an LLM call.

Resolution is best-effort and stays inside the scanned file set. Imports that
point at third-party packages or the standard library never match a local file,
so they simply drop out instead of inflating the ranking.
"""

from __future__ import annotations

import posixpath
import re
from collections import defaultdict, deque
from pathlib import PurePosixPath

_PY_IMPORT = re.compile(r"^\s*import\s+(.+)$")
_PY_FROM = re.compile(r"^\s*from\s+(\.*)([\w.]*)\s+import\s+(.+)$")

_JS_FROM = re.compile(r"""\bfrom\s*['"]([^'"]+)['"]""")
_JS_BARE = re.compile(r"""\bimport\s*['"]([^'"]+)['"]""")
_JS_REQUIRE = re.compile(r"""\brequire\s*\(\s*['"]([^'"]+)['"]\s*\)""")
_JS_DYNAMIC = re.compile(r"""\bimport\s*\(\s*['"]([^'"]+)['"]\s*\)""")

_PY_LANGS = {"python"}
_JS_LANGS = {"javascript", "typescript", "jsx", "tsx", "vue", "svelte"}
_JS_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte")

# keep the dependents list small enough to ship in the API response
_MAX_DEPENDENTS = 12

# conventional entry-point file names, checked without extension/case
_ENTRY_HINTS = {
    "main",
    "app",
    "cli",
    "__main__",
    "index",
    "server",
    "run",
    "manage",
    "wsgi",
    "asgi",
}


def _posix(path: str) -> str:
    return path.replace("\\", "/")


def _py_module_name(path: str) -> str | None:
    """Dotted module name for a python file, or None if it isn't one."""
    if path == "__init__.py":
        return ""
    if path.endswith("/__init__.py"):
        return path[: -len("/__init__.py")].replace("/", ".")
    if path.endswith(".py"):
        return path[: -len(".py")].replace("/", ".")
    return None


def _py_package(path: str) -> str:
    """Package a python file lives in, used to resolve relative imports."""
    mod = _py_module_name(path)
    if mod is None:
        return ""
    if path.endswith("__init__.py"):
        return mod
    return mod.rsplit(".", 1)[0] if "." in mod else ""


def _match_module(dotted: str, py_modules: dict[str, str]) -> str | None:
    """Resolve a dotted name to a scanned file, falling back to its prefixes.

    ``import a.b.c`` where ``c`` is an attribute still resolves to ``a/b.py``.
    """
    parts = dotted.split(".")
    while parts:
        cand = ".".join(parts)
        if cand in py_modules:
            return py_modules[cand]
        parts.pop()
    return None


def _resolve_relative(pkg: str, levels: int, module: str) -> str | None:
    """Turn a relative import (``from ..x import y``) into an absolute base."""
    if levels == 0:
        return module
    base_parts = pkg.split(".") if pkg else []
    drop = levels - 1
    if drop:
        if drop > len(base_parts):
            return None
        base_parts = base_parts[:-drop]
    base = ".".join(base_parts)
    if module:
        return f"{base}.{module}" if base else module
    return base


def _py_edges(content: str, current: str, py_modules: dict[str, str]) -> set[str]:
    pkg = _py_package(current)
    resolved: set[str] = set()

    for line in content.splitlines():
        m = _PY_IMPORT.match(line)
        if m:
            for part in m.group(1).split("#")[0].split(","):
                name = part.strip().split(" as ")[0].strip()
                hit = _match_module(name, py_modules) if name else None
                if hit:
                    resolved.add(hit)
            continue

        m = _PY_FROM.match(line)
        if not m:
            continue
        dots, module, raw_names = m.group(1), m.group(2), m.group(3)
        base = _resolve_relative(pkg, len(dots), module)
        if base is None:
            continue

        matched_name = False
        names = raw_names.split("#")[0].replace("(", " ").replace(")", " ")
        for raw in names.split(","):
            name = raw.strip().split(" as ")[0].strip()
            if not name or name == "*":
                continue
            cand = f"{base}.{name}" if base else name
            hit = _match_module(cand, py_modules)
            if hit:
                resolved.add(hit)
                matched_name = True
        # the names were plain attributes, so the dependency is the module itself
        if not matched_name and base:
            hit = _match_module(base, py_modules)
            if hit:
                resolved.add(hit)

    resolved.discard(current)
    return resolved


def _js_specifiers(content: str) -> list[str]:
    specs = _JS_FROM.findall(content)
    specs += _JS_BARE.findall(content)
    specs += _JS_REQUIRE.findall(content)
    specs += _JS_DYNAMIC.findall(content)
    return specs


def _resolve_js_file(base: str, file_set: set[str]) -> str | None:
    if base in file_set:
        return base
    for ext in _JS_EXTS:
        if base + ext in file_set:
            return base + ext
    for ext in _JS_EXTS:
        cand = f"{base}/index{ext}"
        if cand in file_set:
            return cand
    return None


def _js_edges(content: str, current: str, file_set: set[str]) -> set[str]:
    cur_dir = str(PurePosixPath(current).parent)
    resolved: set[str] = set()

    for spec in _js_specifiers(content):
        spec = spec.split("?")[0].split("#")[0]
        if not spec.startswith("."):
            continue  # bare specifier -> third-party, not a local file
        base = posixpath.normpath(posixpath.join(cur_dir, spec))
        hit = _resolve_js_file(base, file_set)
        if hit and hit != current:
            resolved.add(hit)

    return resolved


def _reason(fan_in: int) -> str:
    if fan_in >= 5:
        return f"项目里有 {fan_in} 个文件用到它，几乎绕不开，是最该先读的核心模块。"
    return f"有 {fan_in} 个文件用到它，是比较核心的模块。"


def rank_hotspots(files: list[dict], *, limit: int = 8) -> list[dict]:
    """Rank scanned files by fan-in (how many other files import them).

    Args:
        files: scanner output dicts with ``path``, ``language`` and ``preview``.
        limit: how many top files to return.

    Returns a list of ``{"path", "language", "fan_in", "dependents", "reason"}``
    sorted by fan-in descending, then path. Files nothing imports are omitted.
    """
    by_path: dict[str, dict] = {}
    file_set: set[str] = set()
    py_modules: dict[str, str] = {}

    for f in files:
        path = _posix(f["path"])
        by_path[path] = f
        file_set.add(path)
        mod = _py_module_name(path)
        if mod is not None:
            py_modules.setdefault(mod, path)

    fan_in: dict[str, set[str]] = defaultdict(set)
    for f in files:
        path = _posix(f["path"])
        lang = f.get("language", "unknown")
        content = f.get("preview") or ""
        if lang in _PY_LANGS:
            deps = _py_edges(content, path, py_modules)
        elif lang in _JS_LANGS:
            deps = _js_edges(content, path, file_set)
        else:
            continue
        for dep in deps:
            fan_in[dep].add(path)

    ranked = [
        {
            "path": path,
            "language": by_path[path].get("language", "unknown"),
            "fan_in": len(importers),
            "dependents": sorted(importers)[:_MAX_DEPENDENTS],
            "reason": _reason(len(importers)),
        }
        for path, importers in fan_in.items()
        if importers
    ]
    ranked.sort(key=lambda h: (-h["fan_in"], h["path"]))
    return ranked[:limit]


def _order_reason(role: str) -> str:
    if role == "entry":
        return "Entry point -- where the program starts; read this first."
    if role == "leaf":
        return "A building block the code above relies on; no further local imports."
    return "Pulled in by what you just read; read it next to follow the flow."


def suggest_reading_order(files: list[dict], *, limit: int = 12) -> list[dict]:
    """Suggest an order to read a project's files for someone new to it.

    Starts from entry points (files nothing else imports, preferring conventional
    names like ``main``/``app``/``cli``) and walks the import graph breadth-first,
    so a reader meets the "front door" first and then the modules it pulls in.
    Like :func:`rank_hotspots` this is deterministic and spends no LLM call.

    Args:
        files: scanner output dicts with ``path``, ``language`` and ``preview``.
        limit: how many steps to return.

    Returns a list of ``{"path", "language", "step", "role", "reason"}`` in the
    order they should be read; ``step`` is 1-based and ``role`` is one of
    ``"entry"``, ``"core"`` or ``"leaf"``.
    """
    by_path: dict[str, dict] = {}
    file_set: set[str] = set()
    py_modules: dict[str, str] = {}

    for f in files:
        path = _posix(f["path"])
        by_path[path] = f
        file_set.add(path)
        mod = _py_module_name(path)
        if mod is not None:
            py_modules.setdefault(mod, path)

    imports: dict[str, set[str]] = {}
    fan_in: dict[str, set[str]] = defaultdict(set)
    for f in files:
        path = _posix(f["path"])
        lang = f.get("language", "unknown")
        content = f.get("preview") or ""
        if lang in _PY_LANGS:
            deps = _py_edges(content, path, py_modules)
        elif lang in _JS_LANGS:
            deps = _js_edges(content, path, file_set)
        else:
            deps = set()
        imports[path] = deps
        for dep in deps:
            fan_in[dep].add(path)

    def _entry_key(path: str) -> tuple[int, int, str]:
        name = path.rsplit("/", 1)[-1]
        stem = name[: -len(".py")] if name.endswith(".py") else name.rsplit(".", 1)[0]
        is_hint = 0 if stem.lower() in _ENTRY_HINTS else 1
        return (is_hint, path.count("/"), path)

    # entry points: in-project files that nothing else imports
    entries = sorted((p for p in by_path if not fan_in.get(p)), key=_entry_key)

    order: list[str] = []
    seen: set[str] = set()
    queue: deque[str] = deque(entries)
    while queue:
        path = queue.popleft()
        if path in seen or path not in by_path:
            continue
        seen.add(path)
        order.append(path)
        for dep in sorted(imports.get(path, ())):
            if dep not in seen:
                queue.append(dep)

    # files unreachable from any entry (isolated or only in a cycle) go last
    for path in sorted(by_path):
        if path not in seen:
            seen.add(path)
            order.append(path)

    result: list[dict] = []
    for step, path in enumerate(order[:limit], start=1):
        if path in entries:
            role = "entry"
        elif imports.get(path):
            role = "core"
        else:
            role = "leaf"
        result.append(
            {
                "path": path,
                "language": by_path[path].get("language", "unknown"),
                "step": step,
                "role": role,
                "reason": _order_reason(role),
            }
        )
    return result


def _build_import_graph(
    files: list[dict],
) -> tuple[dict[str, dict], dict[str, set[str]], dict[str, set[str]]]:
    """Build the in-project import graph shared by the analysis helpers.

    Returns ``(by_path, imports, fan_in)`` where ``imports[p]`` is the set of
    scanned files ``p`` imports and ``fan_in[p]`` is the set that import ``p``.
    """
    by_path: dict[str, dict] = {}
    file_set: set[str] = set()
    py_modules: dict[str, str] = {}
    for f in files:
        path = _posix(f["path"])
        by_path[path] = f
        file_set.add(path)
        mod = _py_module_name(path)
        if mod is not None:
            py_modules.setdefault(mod, path)

    imports: dict[str, set[str]] = {}
    fan_in: dict[str, set[str]] = defaultdict(set)
    for f in files:
        path = _posix(f["path"])
        lang = f.get("language", "unknown")
        content = f.get("preview") or ""
        if lang in _PY_LANGS:
            deps = _py_edges(content, path, py_modules)
        elif lang in _JS_LANGS:
            deps = _js_edges(content, path, file_set)
        else:
            deps = set()
        imports[path] = deps
        for dep in deps:
            fan_in[dep].add(path)
    return by_path, imports, fan_in


def _strongly_connected_components(imports: dict[str, set[str]]) -> list[list[str]]:
    """Tarjan's SCC algorithm (iterative, so deep graphs don't blow the stack).

    Node and neighbour iteration is sorted, making the output deterministic.
    """
    index_of: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    components: list[list[str]] = []
    counter = 0

    for root in sorted(imports):
        if root in index_of:
            continue
        # work stack of (node, iterator over its neighbours)
        work: list[tuple[str, list[str]]] = [(root, sorted(imports.get(root, ())))]
        index_of[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            node, neighbours = work[-1]
            advanced = False
            while neighbours:
                nxt = neighbours.pop(0)
                if nxt not in imports:  # import points outside the scanned set
                    continue
                if nxt not in index_of:
                    index_of[nxt] = low[nxt] = counter
                    counter += 1
                    stack.append(nxt)
                    on_stack.add(nxt)
                    work.append((nxt, sorted(imports.get(nxt, ()))))
                    advanced = True
                    break
                if nxt in on_stack:
                    low[node] = min(low[node], index_of[nxt])
            if advanced:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index_of[node]:
                component: list[str] = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    component.append(w)
                    if w == node:
                        break
                components.append(sorted(component))
    return components


def find_import_cycles(files: list[dict], *, limit: int = 8) -> list[dict]:
    """Find groups of files that import each other in a cycle.

    Circular imports make a codebase harder to read and refactor — you can't
    understand one file without the others, and they invite import-time errors.
    Returns each strongly-connected component of more than one file in the
    import graph, largest first. Deterministic and spends no LLM call.

    Returns a list of ``{"files", "size", "reason"}``.
    """
    _, imports, _ = _build_import_graph(files)
    cycles = [comp for comp in _strongly_connected_components(imports) if len(comp) > 1]
    cycles.sort(key=lambda c: (-len(c), c[0]))
    return [
        {
            "files": comp,
            "size": len(comp),
            "reason": (
                f"这 {len(comp)} 个文件互相 import 形成依赖环，"
                "建议放在一起读、并考虑解开循环以降低耦合。"
            ),
        }
        for comp in cycles[:limit]
    ]
