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


def _coupling_reason(fan_out: int) -> str:
    if fan_out >= 5:
        return f"它直接依赖 {fan_out} 个本地模块，耦合很高，是优先的重构/拆分候选。"
    return f"它依赖 {fan_out} 个本地模块，耦合中等。"


def rank_coupling(files: list[dict], *, limit: int = 8) -> list[dict]:
    """Rank scanned files by fan-out (how many local modules each one imports).

    The inverse lens to :func:`rank_hotspots`: hotspots are the most depended-on
    (core) files, whereas high fan-out files depend on the most others, so they
    carry the most coupling and are the prime refactoring/splitting candidates.

    Args:
        files: scanner output dicts with ``path``, ``language`` and ``preview``.
        limit: how many top files to return.

    Returns a list of ``{"path", "language", "fan_out", "dependencies", "reason"}``
    sorted by fan-out descending, then path. Files that import no local module
    are omitted.
    """
    file_set: set[str] = set()
    py_modules: dict[str, str] = {}

    for f in files:
        path = _posix(f["path"])
        file_set.add(path)
        mod = _py_module_name(path)
        if mod is not None:
            py_modules.setdefault(mod, path)

    ranked: list[dict] = []
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
        deps.discard(path)  # a self-import is not coupling to another module
        if not deps:
            continue
        ranked.append(
            {
                "path": path,
                "language": lang,
                "fan_out": len(deps),
                "dependencies": sorted(deps)[:_MAX_DEPENDENTS],
                "reason": _coupling_reason(len(deps)),
            }
        )
    ranked.sort(key=lambda h: (-h["fan_out"], h["path"]))
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


def find_orphan_modules(files: list[dict], *, limit: int = 8) -> list[dict]:
    """Find code files that are disconnected from the import graph.

    A file that nothing imports and that imports nothing else in the project is
    an island: dead code, a stray script, or a module that should be wired in
    but isn't. This is different from an entry point — an entry point is also
    imported by nothing, but it *does* pull in other modules, while an orphan
    has no edges at all. Only files in languages the graph understands (Python /
    JS-TS) are considered, so docs and config never show up. Deterministic and
    spends no LLM call.

    Returns a list of ``{"path", "language", "reason"}`` sorted by path.
    """
    by_path, imports, fan_in = _build_import_graph(files)
    orphans: list[dict] = []
    for path in sorted(by_path):
        f = by_path[path]
        lang = f.get("language", "unknown")
        if lang not in _PY_LANGS and lang not in _JS_LANGS:
            continue
        if imports.get(path) or fan_in.get(path):
            continue
        orphans.append(
            {
                "path": path,
                "language": lang,
                "reason": (
                    "没有任何文件 import 它，它也不 import 项目里的其他文件，"
                    "是脱离依赖图的孤岛——可能是死代码、独立脚本，或漏接的模块。"
                ),
            }
        )
    return orphans[:limit]


def _blast_reason(blast: int, direct: int) -> str:
    if blast >= 5:
        return f"改它会波及 {blast} 个文件（其中 {direct} 个直接依赖），改动前最该先评估影响范围。"
    return f"改它大约波及 {blast} 个文件，影响范围中等。"


def rank_blast_radius(files: list[dict], *, limit: int = 8) -> list[dict]:
    """Rank files by how many other files *transitively* depend on them.

    Where :func:`rank_hotspots` counts direct importers, this follows the import
    edges in reverse to its closure: if changing a file could ripple to N other
    files (its importers, their importers, and so on), that N is its blast
    radius. It answers the newcomer's "if I change this, what might break?" much
    more honestly than direct fan-in, since impact propagates through the graph.
    Cycles are handled by the visited set. Deterministic and spends no LLM call.

    Args:
        files: scanner output dicts with ``path``, ``language`` and ``preview``.
        limit: how many top files to return.

    Returns a list of
    ``{"path", "language", "blast_radius", "direct_dependents", "reason"}``
    sorted by blast radius descending, then path. Files nothing depends on are
    omitted.
    """
    by_path, _imports, fan_in = _build_import_graph(files)

    ranked: list[dict] = []
    for path in by_path:
        # reverse BFS along fan_in edges: every file that (transitively) imports
        # ``path`` and would therefore be in the blast radius of changing it.
        seen: set[str] = set()
        queue: deque[str] = deque(fan_in.get(path, ()))
        while queue:
            dep = queue.popleft()
            if dep in seen or dep == path:
                continue
            seen.add(dep)
            for upstream in fan_in.get(dep, ()):
                if upstream not in seen and upstream != path:
                    queue.append(upstream)
        if not seen:
            continue
        ranked.append(
            {
                "path": path,
                "language": by_path[path].get("language", "unknown"),
                "blast_radius": len(seen),
                "direct_dependents": sorted(fan_in.get(path, ()))[:_MAX_DEPENDENTS],
                "reason": _blast_reason(len(seen), len(fan_in.get(path, set()))),
            }
        )
    ranked.sort(key=lambda h: (-h["blast_radius"], h["path"]))
    return ranked[:limit]


def _layer_reason(layer: int) -> str:
    if layer == 0:
        return "地基层：不依赖项目里的其他文件，被上层模块复用，最稳定，最该先读懂。"
    return f"第 {layer} 层：叠在 {layer} 层本地依赖之上，越往上越接近应用入口和编排逻辑。"


def assign_architecture_layers(files: list[dict], *, limit: int = 12) -> list[dict]:
    """Stratify the project's code files into dependency layers.

    Cycles are condensed into single nodes (via SCCs) so the layering graph is
    acyclic, then each file gets a layer equal to the longest chain of local
    imports beneath it: files that import nothing local sit at layer 0 (the
    foundation everything builds on), and each layer above imports the one
    below, up to the entry/orchestration files. Unlike a reading order (a flat
    sequence) this shows the *shape* of a codebase as tiers. Deterministic and
    spends no LLM call.

    Args:
        files: scanner output dicts with ``path``, ``language`` and ``preview``.
        limit: how many files to return (highest layers first).

    Returns a list of ``{"path", "language", "layer", "reason"}`` sorted by layer
    descending, then path. Only Python / JS-TS files are layered.
    """
    by_path, imports, _fan_in = _build_import_graph(files)

    # condense cycles so the layering graph is acyclic
    scc_of: dict[str, int] = {}
    for i, comp in enumerate(_strongly_connected_components(imports)):
        for node in comp:
            scc_of[node] = i

    scc_imports: dict[int, set[int]] = defaultdict(set)
    for path, deps in imports.items():
        a = scc_of.get(path)
        if a is None:
            continue
        for dep in deps:
            b = scc_of.get(dep)
            if b is not None and b != a:
                scc_imports[a].add(b)

    # longest path to a leaf on the condensed DAG; memoized, acyclic so it ends
    layer_cache: dict[int, int] = {}

    def _scc_layer(scc: int) -> int:
        if scc not in layer_cache:
            deps = scc_imports.get(scc, ())
            layer_cache[scc] = 1 + max((_scc_layer(d) for d in deps), default=-1)
        return layer_cache[scc]

    result: list[dict] = []
    for path in by_path:
        lang = by_path[path].get("language", "unknown")
        if lang not in _PY_LANGS and lang not in _JS_LANGS:
            continue
        scc = scc_of.get(path)
        layer = _scc_layer(scc) if scc is not None else 0
        result.append(
            {
                "path": path,
                "language": lang,
                "layer": layer,
                "reason": _layer_reason(layer),
            }
        )
    result.sort(key=lambda h: (-h["layer"], h["path"]))
    return result[:limit]


def _package_of(path: str) -> str:
    """The directory a file lives in, used as its package label."""
    posix = _posix(path)
    return posix.rsplit("/", 1)[0] if "/" in posix else "(root)"


def _package_reason(fan_out: int, fan_in: int) -> str:
    if fan_in and not fan_out:
        return (
            f"被 {fan_in} 个其他目录依赖、自己不依赖别的目录："
            "偏底层的公共能力，改动影响面最大，值得先读懂。"
        )
    if fan_out and not fan_in:
        return (
            f"依赖 {fan_out} 个其他目录、没有目录反过来依赖它："
            "偏上层的入口 / 编排，适合从这里顺着依赖往下读。"
        )
    return f"依赖 {fan_out} 个目录、又被 {fan_in} 个目录依赖：处在架构中段，是连接上下层的枢纽。"


def summarize_package_dependencies(files: list[dict], *, limit: int = 12) -> list[dict]:
    """Condense the file-level import graph into a directory-level one.

    Each file is labelled by the directory it lives in, and same-directory
    imports are dropped, so the result is a high-level map of which folders lean
    on which. It answers "how do the big pieces fit together" without making a
    reader open a single file. Deterministic and spends no LLM call.

    Args:
        files: scanner output dicts with ``path``, ``language`` and ``preview``.
        limit: how many packages to return (most cross-package coupling first).

    Returns a list of ``{"package", "depends_on", "depended_on_by", "fan_out",
    "fan_in", "reason"}`` sorted by total cross-package coupling descending, then
    package. Directories with no cross-directory imports are omitted.
    """
    _by_path, imports, _fan_in = _build_import_graph(files)
    pkg_of = {path: _package_of(path) for path in imports}

    depends_on: dict[str, set[str]] = defaultdict(set)
    depended_on_by: dict[str, set[str]] = defaultdict(set)
    for path, deps in imports.items():
        a = pkg_of[path]
        for dep in deps:
            b = pkg_of.get(dep)
            if b is None or b == a:
                continue
            depends_on[a].add(b)
            depended_on_by[b].add(a)

    result: list[dict] = []
    for pkg in set(depends_on) | set(depended_on_by):
        outs = sorted(depends_on.get(pkg, ()))
        ins = sorted(depended_on_by.get(pkg, ()))
        result.append(
            {
                "package": pkg,
                "depends_on": outs,
                "depended_on_by": ins,
                "fan_out": len(outs),
                "fan_in": len(ins),
                "reason": _package_reason(len(outs), len(ins)),
            }
        )
    result.sort(key=lambda d: (-(d["fan_in"] + d["fan_out"]), d["package"]))
    return result[:limit]


def summarize_project_health(files: list[dict]) -> dict:
    """A one-glance, plain-language health read of the project's structure.

    Rolls the per-file / per-directory analyses up to project level so a
    non-programmer can size up a codebase at a glance: how big it is, what its
    load-bearing file is, and where the structural risks (circular imports,
    orphan files, wide change blast radius) are. Deterministic, no LLM call.

    Returns a dict of totals, risk counts, the single most-depended-on file, the
    widest change blast radius, and a list of plain-language ``notes``.
    """
    by_path, imports, fan_in = _build_import_graph(files)
    code = [
        path
        for path in by_path
        if by_path[path].get("language") in _PY_LANGS or by_path[path].get("language") in _JS_LANGS
    ]
    total_code_files = len(code)
    total_directories = len({_package_of(path) for path in code})
    cycle_groups = sum(1 for comp in _strongly_connected_components(imports) if len(comp) > 1)
    orphan_files = sum(1 for path in code if not imports.get(path) and not fan_in.get(path))

    core = rank_hotspots(files, limit=1)
    blast = rank_blast_radius(files, limit=1)
    most_depended_on = core[0]["path"] if core else ""
    most_depended_on_fan_in = core[0]["fan_in"] if core else 0
    widest_blast_radius_file = blast[0]["path"] if blast else ""
    widest_blast_radius = blast[0]["blast_radius"] if blast else 0

    notes: list[str] = [
        f"项目里有 {total_code_files} 个代码文件，分布在 {total_directories} 个目录。"
    ]
    if most_depended_on:
        notes.append(
            f"最核心的文件是 {most_depended_on}"
            f"（被 {most_depended_on_fan_in} 个文件依赖），建议最先读懂。"
        )
    if widest_blast_radius > 0:
        notes.append(
            f"改动影响面最大的是 {widest_blast_radius_file}"
            f"（牵连约 {widest_blast_radius} 个文件），改它要格外小心。"
        )
    if cycle_groups:
        notes.append(f"发现 {cycle_groups} 组循环依赖，建议理清以降低耦合。")
    else:
        notes.append("没有循环依赖，依赖关系是干净的有向结构。")
    if orphan_files:
        notes.append(
            f"有 {orphan_files} 个文件和其他文件没有任何 import 关系，可能是死代码或漏接的模块。"
        )

    return {
        "total_code_files": total_code_files,
        "total_directories": total_directories,
        "circular_dependency_groups": cycle_groups,
        "orphan_files": orphan_files,
        "most_depended_on": most_depended_on,
        "most_depended_on_fan_in": most_depended_on_fan_in,
        "widest_blast_radius_file": widest_blast_radius_file,
        "widest_blast_radius": widest_blast_radius,
        "notes": notes,
    }


def _mermaid_node_id(name: str) -> str:
    """A Mermaid-safe node id for a package label (kept stable and unique)."""
    return "n_" + re.sub(r"[^A-Za-z0-9_]", "_", name)


def _codemap_mermaid(packages: list[dict]) -> str:
    """Build a Mermaid flowchart of the directory-dependency edges.

    Rendered inline by GitHub and other Markdown viewers, so the exported map
    carries a visual architecture diagram, not just lists. Returns "" when there
    are no cross-directory edges to draw.
    """
    nodes: dict[str, str] = {}
    edges: set[tuple[str, str]] = set()
    for pkg in packages:
        a = _mermaid_node_id(pkg["package"])
        nodes[a] = pkg["package"]
        for dep in pkg["depends_on"]:
            b = _mermaid_node_id(dep)
            nodes[b] = dep
            edges.add((a, b))
    if not edges:
        return ""
    lines = ["flowchart TD"]
    lines.extend(f'    {nid}["{label}/"]' for nid, label in sorted(nodes.items()))
    lines.extend(f"    {a} --> {b}" for a, b in sorted(edges))
    return "\n".join(lines)


def render_codemap_markdown(project_name: str, files: list[dict]) -> str:
    """Render the full deterministic code map as a shareable Markdown document.

    Bundles every import-graph analysis (health, core files, layers, directory
    dependencies, cycles, blast radius, coupling, orphans) into one document a
    reader can save, share, or paste into a PR. Sections with nothing to show
    are omitted so small projects stay short. Deterministic, no LLM call.
    """
    lines = [
        f"# {project_name} — 代码地图",
        "",
        "> 这份结构速览直接从文件之间的 import 关系算出，不依赖 AI。",
        "",
    ]

    health = summarize_project_health(files)
    if health["notes"]:
        lines.append("## 项目体检")
        lines.append("")
        lines.extend(f"- {note}" for note in health["notes"])
        lines.append("")

    hotspots = rank_hotspots(files)
    if hotspots:
        lines.append("## 核心文件（被依赖最多）")
        lines.append("")
        lines.extend(f"- `{h['path']}` — {h['reason']}" for h in hotspots)
        lines.append("")

    layers = assign_architecture_layers(files)
    if layers:
        lines.append("## 架构分层（第 0 层是地基，越往上越接近入口）")
        lines.append("")
        lines.extend(f"- L{a['layer']} `{a['path']}`" for a in layers)
        lines.append("")

    packages = summarize_package_dependencies(files)
    if packages:
        lines.append("## 目录之间怎么依赖")
        lines.append("")
        for p in packages:
            deps = "、".join(p["depends_on"])
            arrow = f" → 依赖 {deps}" if deps else ""
            lines.append(f"- `{p['package']}/`{arrow}")
            lines.append(f"  - {p['reason']}")
        lines.append("")
        mermaid = _codemap_mermaid(packages)
        if mermaid:
            lines.append("### 目录依赖图")
            lines.append("")
            lines.append("```mermaid")
            lines.append(mermaid)
            lines.append("```")
            lines.append("")

    cycles = find_import_cycles(files)
    if cycles:
        lines.append("## 循环依赖（文件互相 import，建议理清）")
        lines.append("")
        for c in cycles:
            chain = " → ".join(f"`{p}`" for p in c["files"])
            lines.append(f"- {chain}")
        lines.append("")

    blast = rank_blast_radius(files)
    if blast:
        lines.append("## 改动影响面（改这些文件波及最广）")
        lines.append("")
        lines.extend(f"- `{b['path']}` — {b['reason']}" for b in blast)
        lines.append("")

    coupling = rank_coupling(files)
    if coupling:
        lines.append("## 依赖最多的文件（牵连其他文件最多）")
        lines.append("")
        lines.extend(f"- `{c['path']}` — {c['reason']}" for c in coupling)
        lines.append("")

    orphans = find_orphan_modules(files)
    if orphans:
        lines.append("## 可能没人用的文件（没有被其他文件 import）")
        lines.append("")
        lines.extend(f"- `{o['path']}` — {o['reason']}" for o in orphans)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
