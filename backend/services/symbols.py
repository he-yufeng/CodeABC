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
           ``const name = (...) =>`` / ``const name = function`` assignments, and
           methods one indent inside a class (recorded with their class).

Each entry carries the name, its kind (function / class / method), the
enclosing class for a method, the file, and a 1-based line number.

Limitations (kept honest on purpose):

  * Matching is regex over indentation, not a real parser. Decorators that
    rename, ``setattr`` / ``globals()`` tricks, conditional re-exports, and
    names built at runtime are out of scope.
  * A name defined in several files yields one entry per file; the caller
    decides which is meant.

The companion lookup :func:`find_references` answers the other half — where a
name is *used*, not just where it is born — by whole-word text search across the
same source files, flagging the occurrence that is the declaration itself.

Every entry also carries an ``exported`` flag — public by Python's underscore
convention or a JS/TS ``export`` — and :func:`public_api` filters the index down
to just that surface, so a reader can see a project's interface before its
internals.
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


def _count_phrase(n: int, kind: str) -> str:
    """'1 class', '2 classes', '1 function' — grammatical for a plain-language note."""
    if kind == "class":
        word = "class" if n == 1 else "classes"
    else:
        word = kind if n == 1 else f"{kind}s"
    return f"{n} {word}"


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
    # frames: (indent, kind, name, exported) for currently open class/def blocks
    frames: list[tuple[int, str, str, bool]] = []

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
        # A name is part of the public surface only when its container is and it
        # follows the convention: no leading underscore.
        parent_exported = _enclosing_exported(enclosing)

        if class_match is not None:
            name = class_match.group("name")
            parent = enclosing[2] if enclosing and enclosing[1] == "class" else None
            exported = parent_exported and not name.startswith("_")
            out.append(_entry(path, "python", name, "class", parent, lineno, exported))
            frames.append((indent, "class", name, exported))
            continue

        assert def_match is not None  # narrowing: class_match is None here
        name = def_match.group("name")
        exported = parent_exported and not name.startswith("_")
        if enclosing is None:
            out.append(_entry(path, "python", name, "function", None, lineno, exported))
            frames.append((indent, "def", name, exported))
        elif enclosing[1] == "class":
            out.append(_entry(path, "python", name, "method", enclosing[2], lineno, exported))
            frames.append((indent, "def", name, exported))
        else:
            # nested inside another def: a local helper — track it so its own
            # nested blocks resolve correctly, but do not index it.
            frames.append((indent, "def", name, False))

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
# A method *declaration* inside a class body: optional TS modifiers, an optional
# get/set or generator marker, the name, a parameter list, an optional TS return
# annotation, and the opening brace on the same line. The trailing ``{`` is what
# separates a declaration (``render() {``) from a call (``render();``).
_JS_METHOD_RE = re.compile(
    r"^\s*(?:(?:public|private|protected|readonly|static|async|override|abstract)\s+)*"
    r"(?:(?:get|set)\s+)?\*?\s*"
    r"(?P<name>" + _IDENT + r")\s*\([^;]*\)\s*(?::[^={};]+)?\{"
)
# Control-flow heads also read as ``word (...) {``; never treat them as methods.
_JS_NON_METHODS = frozenset(
    {"if", "for", "while", "switch", "catch", "do", "with", "return", "function", "else"}
)
# A top-level declaration is part of the public surface only when it is exported.
_JS_EXPORT_RE = re.compile(r"^\s*export\b")


def _js_line_exported(raw: str) -> bool:
    """True when a declaration line begins with ``export`` (``export default`` too)."""
    return bool(_JS_EXPORT_RE.match(raw))


def _js_method_private(raw: str) -> bool:
    """True when a method carries a ``private`` / ``protected`` TS modifier.

    Modifiers sit before the name and parameter list, so the words ahead of the
    first ``(`` are enough to decide; ``#``-prefixed private fields never reach
    here because they are not matched as methods in the first place.
    """
    prefix = raw.strip().split("(", 1)[0]
    tokens = prefix.split()
    return "private" in tokens or "protected" in tokens


def _js_definitions(path: str, content: str) -> list[dict]:
    out: list[dict] = []
    # frames: (indent, kind, name, exported) for currently open class/block scopes,
    # mirroring the Python pass so a method is only read inside a class body and a
    # method's own body is not re-scanned for nested "methods".
    frames: list[tuple[int, str, str, bool]] = []

    for lineno, raw in enumerate(content.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("//"):
            continue

        indent = _indent_width(raw)
        while frames and frames[-1][0] >= indent:
            frames.pop()
        enclosing = frames[-1] if frames else None
        # In JS/TS the public surface is what the module exports, not a naming
        # convention; a member is only reachable when its container is too.
        parent_exported = _enclosing_exported(enclosing)

        class_match = _JS_CLASS_RE.match(raw)
        if class_match:
            name = class_match.group(1)
            parent = enclosing[2] if enclosing and enclosing[1] == "class" else None
            exported = parent_exported and _js_line_exported(raw)
            out.append(_entry(path, "js", name, "class", parent, lineno, exported))
            frames.append((indent, "class", name, exported))
            continue

        func_match = _JS_FUNC_RE.match(raw)
        if func_match:
            name = func_match.group(1)
            exported = parent_exported and _js_line_exported(raw)
            out.append(_entry(path, "js", name, "function", None, lineno, exported))
            frames.append((indent, "block", name, exported))
            continue

        assign_match = _JS_ASSIGN_RE.match(raw)
        if assign_match:
            name = assign_match.group(1)
            exported = parent_exported and _js_line_exported(raw)
            out.append(_entry(path, "js", name, "function", None, lineno, exported))
            frames.append((indent, "block", name, exported))
            continue

        if enclosing is not None and enclosing[1] == "class":
            method_match = _JS_METHOD_RE.match(raw)
            if method_match:
                name = method_match.group("name")
                if name not in _JS_NON_METHODS:
                    exported = parent_exported and not _js_method_private(raw)
                    out.append(_entry(path, "js", name, "method", enclosing[2], lineno, exported))
                    frames.append((indent, "block", name, exported))

    return out


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def _entry(
    path: str,
    lang: str,
    name: str,
    kind: str,
    parent: str | None,
    line: int,
    exported: bool,
) -> dict:
    qualname = f"{parent}.{name}" if parent else name
    return {
        "name": name,
        "qualname": qualname,
        "kind": kind,
        "parent": parent,
        "lang": lang,
        "file": path,
        "line": line,
        "exported": exported,
    }


def _enclosing_exported(enclosing: tuple | None) -> bool:
    """Whether a definition directly inside ``enclosing`` can be public.

    Module level (no enclosing frame) and the body of a public class can hold
    public names. The body of a function — or of a non-public class — cannot,
    so a name born there is internal no matter what it is called.
    """
    if enclosing is None:
        return True
    if enclosing[1] == "class":
        return bool(enclosing[3])
    return False


def _build_notes(definitions: list[dict], file_contents: dict[str, str]) -> list[str]:
    notes: list[str] = []
    scanned = sum(1 for p in file_contents if _lang(p) in ("python", "js"))
    if scanned == 0:
        notes.append("No Python or JS/TS files were found to index.")
        return notes

    by_kind: dict[str, int] = {}
    for d in definitions:
        by_kind[d["kind"]] = by_kind.get(d["kind"], 0) + 1
    parts = [_count_phrase(by_kind[k], k) for k in sorted(by_kind)]
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


# ---------------------------------------------------------------------------
# Public surface — the names a project means to expose, not its internals
# ---------------------------------------------------------------------------


def public_api(file_contents: dict[str, str], *, limit: int = 2000) -> dict:
    """Return the project's public surface — the names other code is meant to call.

    Where :func:`build_definition_index` lists *every* definition, this keeps
    only the ones a project exposes on purpose, so a reader sees the interface
    before the internals. The rule follows each language's own convention:

      Python   a name is public unless it starts with an underscore, and a
               method is public only when its class is too — so ``_helper`` and
               ``Scanner.__init__`` are internal.
      JS / TS  a name is public when it is ``export``-ed, and a method is public
               when its class is exported and it is not declared ``private`` /
               ``protected``.

    Returns ``{"total", "definitions", "notes"}`` with the same entry shape as
    the definition index (each entry already carries an ``exported`` flag),
    alphabetically sorted and truncated to ``limit``.
    """
    index = build_definition_index(file_contents, limit=100_000)
    public = [d for d in index["definitions"] if d.get("exported")]
    total = len(public)
    notes = _public_api_notes(public, total, file_contents)
    return {"total": total, "definitions": public[:limit], "notes": notes}


def _public_api_notes(public: list[dict], total: int, file_contents: dict[str, str]) -> list[str]:
    langs = {_lang(p) for p in file_contents}
    has_py = "python" in langs
    has_js = "js" in langs
    if not (has_py or has_js):
        return ["No Python or JS/TS files were found to index."]
    if total == 0:
        return [
            "No public names were found: every definition is underscore-prefixed "
            "(Python) or not exported (JS/TS)."
        ]

    by_kind: dict[str, int] = {}
    for d in public:
        by_kind[d["kind"]] = by_kind.get(d["kind"], 0) + 1
    parts = [_count_phrase(by_kind[k], k) for k in sorted(by_kind)]
    notes = [f"{total} public name(s) make up the surface: {', '.join(parts)}."]

    rules: list[str] = []
    if has_py:
        rules.append("Python counts a name as public when it has no leading underscore")
    if has_js:
        rules.append("JS/TS counts a name as public when it is exported")
    notes.append(f"{'; '.join(rules)}.")

    notes.append(
        "Convention-based: a name shown here may still be internal (exported only "
        "for tests, say), and __all__ or re-export lists are not consulted."
    )
    return notes


# ---------------------------------------------------------------------------
# References — where a name is used, not just where it is defined
# ---------------------------------------------------------------------------


def find_references(file_contents: dict[str, str], name: str, *, limit: int = 200) -> dict:
    """Return every place ``name`` appears as a whole word — its use sites.

    This is the other half of :func:`find_definition`: where that points at the
    one line a name is born, this lists every line it shows up on, with a
    trimmed one-line preview and an ``is_definition`` flag so the UI can tell the
    declaration apart from the call sites. Matching is whole-word and
    case-sensitive (``scan`` does not match ``scanner``, ``rescan`` or
    ``my_scan``), and an attribute access like ``self.scan`` counts as a use.

    Returns ``{"name", "total", "files", "references", "notes"}`` where
    ``references`` is ordered by file then line and truncated to ``limit`` while
    ``total`` and ``files`` count every match.

    Limitations (kept honest, same as the definition index): it is text search,
    not a parser. A use hidden inside a string literal or a comment may be
    missed, and a same-named attribute on an unrelated object may be counted.
    """
    target = (name or "").strip()
    if not target:
        return {"name": name, "total": 0, "files": 0, "references": [], "notes": []}

    pattern = re.compile(r"(?<![\w$])" + re.escape(target) + r"(?![\w$])")

    index = build_definition_index(file_contents, limit=100_000)
    def_sites = {(d["file"], d["line"]) for d in index["definitions"] if d["name"] == target}

    references: list[dict] = []
    for path in sorted(file_contents):
        if _lang(path) not in ("python", "js"):
            continue
        for lineno, raw in enumerate(file_contents[path].splitlines(), start=1):
            stripped = raw.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("//"):
                continue
            if not pattern.search(raw):
                continue
            references.append(
                {
                    "name": target,
                    "file": path,
                    "line": lineno,
                    "text": stripped,
                    "is_definition": (path, lineno) in def_sites,
                }
            )

    references.sort(key=lambda r: (r["file"], r["line"]))
    total = len(references)
    files = len({r["file"] for r in references})
    notes = _reference_notes(target, references, total, files, file_contents)
    return {
        "name": target,
        "total": total,
        "files": files,
        "references": references[:limit],
        "notes": notes,
    }


def _reference_notes(
    target: str, references: list[dict], total: int, files: int, file_contents: dict[str, str]
) -> list[str]:
    scanned = sum(1 for p in file_contents if _lang(p) in ("python", "js"))
    if scanned == 0:
        return ["No Python or JS/TS files were found to search."]
    if total == 0:
        return [
            f"'{target}' is not used in any Python or JS/TS file "
            "(or it only appears inside strings or comments)."
        ]

    notes = [f"Found {total} reference(s) to '{target}' across {files} file(s)."]
    def_count = sum(1 for r in references if r["is_definition"])
    if def_count:
        where = "is where" if def_count == 1 else "are where"
        notes.append(f"{def_count} of these {where} '{target}' is defined; the rest are uses.")
    notes.append(
        "Whole-word text search: a use hidden inside a string or comment may be "
        "missed, and a same-named field on an unrelated object may be counted."
    )
    return notes


# ---------------------------------------------------------------------------
# File outline — one file's structure, in the order it is written
# ---------------------------------------------------------------------------


def file_outline(file_contents: dict[str, str], path: str, *, limit: int = 1000) -> dict:
    """Return one file's table of contents, in source order.

    Where :func:`build_definition_index` flattens the whole project
    alphabetically, this answers the question a reader has the moment they open
    an unfamiliar file: "what is in here, top to bottom?". Top-level functions
    and classes are listed in the order they appear, and a class carries its
    methods nested underneath (also in source order), so the shape of the file
    is visible before any of its detail.

    Returns ``{"file", "lang", "total", "outline", "notes"}``. ``outline`` is a
    list of entries (see :func:`_entry`) in line order; an entry that can hold
    nested definitions — a class — gains a ``children`` list with its methods
    (and any nested classes). ``total`` counts every definition, nested ones
    included, before the ``limit`` truncation.
    """
    content = file_contents.get(path)
    if content is None:
        return {
            "file": path,
            "lang": _lang(path),
            "total": 0,
            "outline": [],
            "notes": [f"'{path}' is not among the analyzed files."],
        }

    lang = _lang(path)
    if lang == "python":
        defs = _py_definitions(path, content)
    elif lang == "js":
        defs = _js_definitions(path, content)
    else:
        return {
            "file": path,
            "lang": lang,
            "total": 0,
            "outline": [],
            "notes": ["The outline covers Python and JS/TS files; this file is neither."],
        }

    total = len(defs)
    classes_by_name: dict[str, dict] = {}
    outline: list[dict] = []
    # Walk in source order so a class is always seen before its own members.
    for d in sorted(defs, key=lambda e: e["line"]):
        node = dict(d)
        parent_node = classes_by_name.get(d["parent"]) if d["parent"] else None
        if parent_node is not None:
            parent_node["children"].append(node)
        else:
            # A method whose class is not itself indexed (an orphan) still gets
            # surfaced at the top level rather than silently dropped.
            outline.append(node)
        if d["kind"] == "class":
            node["children"] = []
            classes_by_name[d["name"]] = node

    notes = _outline_notes(path, lang, defs, total)
    return {
        "file": path,
        "lang": lang,
        "total": total,
        "outline": outline[:limit],
        "notes": notes,
    }


def _outline_notes(path: str, lang: str, defs: list[dict], total: int) -> list[str]:
    name = path.rsplit("/", 1)[-1]
    if total == 0:
        return [f"No top-level functions or classes were found in {name}."]

    by_kind: dict[str, int] = {}
    for d in defs:
        by_kind[d["kind"]] = by_kind.get(d["kind"], 0) + 1
    parts = [_count_phrase(by_kind[k], k) for k in sorted(by_kind)]
    notes = [f"{name} defines {', '.join(parts)}, listed in the order they appear."]
    if lang == "js":
        notes.append(
            "For JS/TS, class methods are broken out when the class body is "
            "conventionally indented; arrow-function fields and computed names "
            "are still listed under the class as a whole."
        )
    notes.append("Regex-based outline: runtime-built or re-exported names may be missed.")
    return notes
