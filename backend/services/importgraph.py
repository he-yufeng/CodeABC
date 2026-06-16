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
from collections import defaultdict
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
