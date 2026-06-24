"""Definition index — where each name in the code is actually defined.

Reading unfamiliar code means constantly hitting a name and wondering "where
does this come from?". A call to ``parse_config``, a ``class Scanner``, an
imported helper — the reader wants the file and line that defines it, not a web
search. This module builds that index from the source CodeABC already loaded,
with no LLM and no language server: it scans for top-level definitions (and one
level of class methods) and records where each one lives, so the UI can offer
"jump to definition" for any name a reader clicks.

It covers the two languages CodeABC annotates today:

  Python   ``def`` / ``async def`` / ``class`` at module level, plus methods
           one indent inside a class (recorded with their enclosing class).
  JS / TS  ``function`` / ``async function`` / ``export function`` / ``class``,
           and ``const name = (...) =>`` / ``const name = function`` style
           assignments.

Each entry carries the name, its kind (function / class / method), the
enclosing class for a method, the file, and a 1-based line number.

Limitations (kept honest on purpose):

  * Matching is regex over indentation, not a real parser. Decorators that
    rename, ``setattr`` / ``globals()`` tricks, conditional re-exports, and
    names built at runtime are out of scope.
  * Only definitions are indexed, not references — this points at where a name
    is born, not everywhere it is used.
  * A name defined in several files yields one entry per file; the caller
    decides which is meant.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_IDENT = r"[A-Za-z_$][\w$]*"


def _lang(path: str) -> str:
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    if ext == "py":
        return "python"
    if ext in ("js", "ts", "jsx", "tsx", "mjs", "cjs"):
        return "js"
    return ext


def _indent_width(line: str) -> int:
    expanded = line.expandtabs(4)
    return len(expanded) - len(expanded.lstrip())


# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------

_PY_DEF_RE = re.compile(r"^(?P<indent>\s*)(?:async\s+)?def\s+(?P<name>\w+)\s*\(")
_PY_CLASS_RE = re.compile(r"^(?P<indent>\s*)class\s+(?P<name>\w+)\s*[:(]")


def _py_definitions(path: str, content: str) -> list[dict]:
    """Top-level functions/classes plus direct (and nested-class) methods.

    A stack of open ``class`` / ``def`` blocks, keyed by indentation, tells us
    what encloses each definition. A ``def`` whose nearest enclosing block is a
    class is a method; a ``def`` nested inside another ``def`` is a local helper
    and is skipped (it is not part of the public reading surface).
    """
    out: list[dict] = []
    # frames: list of (indent, kind, name) for currently open class/def blocks
    frames: list[tuple[int, str, str]] = []

    for lineno, raw in enumerate(content.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue

        class_match = _PY_CLASS_RE.match(raw)
        def_match = None if class_match else _PY_DEF_RE.match(raw)
        if class_match is None and def_match is None:
            continue

        indent = _indent_width(raw)
        # close every block that this line is not nested inside
        while frames and frames[-1][0] >= indent:
            frames.pop()
        enclosing = frames[-1] if frames else None

        if class_match is not None:
            name = class_match.group("name")
            parent = enclosing[2] if enclosing and enclosing[1] == "class" else None
            out.append(_entry(path, "python", name, "class", parent, lineno))
            frames.append((indent, "class", name))
            continue

        assert def_match is not None  # narrowing: class_match is None here
        name = def_match.group("name")
        if enclosing is None:
            out.append(_entry(path, "python", name, "function", None, lineno))
            frames.append((indent, "def", name))
        elif enclosing[1] == "class":
            out.append(_entry(path, "python", name, "method", enclosing[2], lineno))
            frames.append((indent, "def", name))
        else:
            # nested inside another def: a local helper — track it so its own
            # nested blocks resolve correctly, but do not index it.
            frames.append((indent, "def", name))

    return out


# ---------------------------------------------------------------------------
# JavaScript / TypeScript
# ---------------------------------------------------------------------------

_JS_FUNC_RE = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*(" + _IDENT + r")\s*\("
)
_JS_CLASS_RE = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+(" + _IDENT + r")\b"
)
# const/let/var name = (...) => ...   or   = async (...) =>   or   = function
_JS_ASSIGN_RE = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:const|let|var)\s+(" + _IDENT + r")\s*=\s*"
    r"(?:async\s+)?(?:function\b|\*?\s*\([^)]*\)\s*=>|" + _IDENT + r"\s*=>)"
)


def _js_definitions(path: str, content: str) -> list[dict]:
    out: list[dict] = []
    for lineno, raw in enumerate(content.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("//"):
            continue

        class_match = _JS_CLASS_RE.match(raw)
        if class_match:
            out.append(_entry(path, "js", class_match.group(1), "class", None, lineno))
            continue

        func_match = _JS_FUNC_RE.match(raw)
        if func_match:
            out.append(_entry(path, "js", func_match.group(1), "function", None, lineno))
            continue

        assign_match = _JS_ASSIGN_RE.match(raw)
        if assign_match:
            out.append(_entry(path, "js", assign_match.group(1), "function", None, lineno))

    return out


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def _entry(path: str, lang: str, name: str, kind: str, parent: str | None, line: int) -> dict:
    qualname = f"{parent}.{name}" if parent else name
    return {
        "name": name,
        "qualname": qualname,
        "kind": kind,
        "parent": parent,
        "lang": lang,
        "file": path,
        "line": line,
    }


def _build_notes(definitions: list[dict], file_contents: dict[str, str]) -> list[str]:
    notes: list[str] = []
    scanned = sum(1 for p in file_contents if _lang(p) in ("python", "js"))
    if scanned == 0:
        notes.append("No Python or JS/TS files were found to index.")
        return notes

    by_kind: dict[str, int] = {}
    for d in definitions:
        by_kind[d["kind"]] = by_kind.get(d["kind"], 0) + 1
    parts = [f"{by_kind[k]} {k}{'es' if k == 'class' else 's'}" for k in sorted(by_kind)]
    if parts:
        notes.append(f"Indexed {', '.join(parts)} across {scanned} source file(s).")

    duplicates = _duplicate_names(definitions)
    if duplicates:
        sample = ", ".join(duplicates[:5])
        notes.append(
            f"{len(duplicates)} name(s) are defined in more than one place "
            f"(e.g. {sample}); a lookup returns every match."
        )

    notes.append(
        "Definitions only: this index shows where a name is declared, not "
        "every place it is used. Matching is regex-based, so runtime-built or "
        "re-exported names may be missed."
    )
    return notes


def _duplicate_names(definitions: list[dict]) -> list[str]:
    seen: dict[str, int] = {}
    for d in definitions:
        seen[d["name"]] = seen.get(d["name"], 0) + 1
    return sorted(name for name, count in seen.items() if count > 1)


def build_definition_index(file_contents: dict[str, str], *, limit: int = 2000) -> dict:
    """Index every top-level definition (and class method) in the project.

    Returns ``{"total", "definitions", "notes"}`` where ``definitions`` is a
    deterministic, alphabetically sorted list of entries (see :func:`_entry`),
    truncated to ``limit``.
    """
    definitions: list[dict] = []
    for path in sorted(file_contents):
        lang = _lang(path)
        content = file_contents[path]
        if lang == "python":
            definitions.extend(_py_definitions(path, content))
        elif lang == "js":
            definitions.extend(_js_definitions(path, content))

    definitions.sort(key=lambda d: (d["name"].lower(), d["file"], d["line"]))
    notes = _build_notes(definitions, file_contents)
    total = len(definitions)
    return {"total": total, "definitions": definitions[:limit], "notes": notes}


def find_definition(file_contents: dict[str, str], name: str, *, limit: int = 50) -> list[dict]:
    """Return the places that define ``name``.

    Tries an exact match first, then falls back to a case-insensitive match so
    a reader who types ``scanner`` still finds ``Scanner``. Results are ordered
    by file then line.
    """
    target = (name or "").strip()
    if not target:
        return []

    index = build_definition_index(file_contents, limit=100_000)
    matches = [d for d in index["definitions"] if d["name"] == target]
    if not matches:
        lowered = target.lower()
        matches = [d for d in index["definitions"] if d["name"].lower() == lowered]

    matches.sort(key=lambda d: (d["file"], d["line"]))
    return matches[:limit]
