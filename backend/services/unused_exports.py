"""Unused exports: public symbols that nothing else in the project references.

Orphan modules answer "which files does nobody import?". This answers the
finer question one level down: "which functions and classes inside otherwise
used files does nobody call?". A public helper that was written for a caller
that no longer exists is dead weight a new reader still has to load into
their head, and it tends to be the code that breaks first in a refactor
because nothing exercises it.

:func:`find_unused_exports` walks the already-read file contents and flags
top-level ``def`` / ``class`` definitions (Python) and ``export``ed
``function`` / ``class`` / ``const`` declarations (JS/TS) whose name never
shows up anywhere outside their own file.

It deliberately stays conservative to keep the signal worth reading:

* Anything decorated is skipped. Decorators are how frameworks register
  things (FastAPI routes, pytest fixtures, click commands, tasks), and a
  decorated definition is used by the framework even when no caller is
  visible in the text.
* Dunder names, private names (leading ``_``), and definitions inside test
  files are skipped. Tests are consumers, not candidates.
* A definition referenced only inside its own module still counts as a
  candidate: a public symbol used only locally is effectively private and
  could have been a ``_helper``.

Findings are *candidates for human review, not verdicts*. String references,
``getattr`` lookups, dynamic imports, and re-export barrels are not tracked,
so anything here deserves a second look before deletion.
"""

from __future__ import annotations

import re

_PY = {"py", "pyi"}
_JSTS = {"js", "jsx", "ts", "tsx", "mjs", "cjs", "mts", "cts"}

_TEST_SEGMENTS = {"test", "tests", "__tests__", "spec", "specs"}

_PY_DEF_RE = re.compile(r"^(async\s+def|def|class)\s+([A-Za-z_][A-Za-z0-9_]*)")
_JS_EXPORT_RE = re.compile(
    r"^\s*export\s+(?:async\s+)?(?:function|class|const|let)\s+([A-Za-z_$][A-Za-z0-9_$]*)"
)

# Names that look dead but are entry points by convention.
_ENTRY_NAMES = {
    "main",
    "app",
    "application",
    "handler",
    "create_app",
    "run",
    "cli",
    "register",
    "setup",
    "teardown",
    "ready",
    "default",
}

_MAX_FINDINGS = 200


def _ext(path: str) -> str:
    name = path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def _is_test(path: str) -> bool:
    norm = path.replace("\\", "/")
    segments = [s for s in norm.split("/") if s]
    if any(s in _TEST_SEGMENTS for s in segments):
        return True
    name = segments[-1] if segments else ""
    stem = name.rsplit(".", 1)[0] if "." in name else name
    return stem.startswith("test_") or stem.endswith("_test") or ".test" in name or ".spec" in name


def _collect_python_defs(path: str, text: str) -> list[dict]:
    """Top-level, undecorated def/class definitions in one Python file."""
    defs: list[dict] = []
    pending_decorated = False
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if stripped.startswith("@"):
            if indent == 0:
                pending_decorated = True
            continue
        if indent != 0:
            pending_decorated = False
            continue
        m = _PY_DEF_RE.match(line)
        if not m:
            pending_decorated = False
            continue
        name = m.group(2)
        decorated = pending_decorated
        pending_decorated = False
        if decorated or name.startswith("_") or name in _ENTRY_NAMES:
            continue
        kind = "class" if m.group(1) == "class" else "function"
        defs.append({"path": path, "name": name, "kind": kind, "line": lineno})
    return defs


def _collect_js_defs(path: str, text: str) -> list[dict]:
    defs: list[dict] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        m = _JS_EXPORT_RE.match(line)
        if not m:
            continue
        name = m.group(1)
        if name.startswith("_") or name in _ENTRY_NAMES:
            continue
        kind = "class" if "class" in line.split("export", 1)[1].split(name)[0] else "function"
        defs.append({"path": path, "name": name, "kind": kind, "line": lineno})
    return defs


def _referenced_outside(name: str, home: str, contents: dict[str, str]) -> bool:
    """True when the name appears anywhere outside its own file.

    Test files count as consumers here: a symbol exercised only by tests is
    alive, it is just not part of the runtime surface.
    """
    word = re.compile(r"\b" + re.escape(name) + r"\b")
    for path, text in contents.items():
        if path == home:
            continue
        if word.search(text):
            return True
    return False


def _referenced_locally_only(name: str, home: str, text: str) -> bool:
    """True when the name is used in its own file beyond the definition line."""
    return len(re.findall(r"\b" + re.escape(name) + r"\b", text)) > 1


def find_unused_exports(file_contents: dict[str, str]) -> dict:
    """Flag public definitions with no references outside their own file.

    Returns a summary dict with ``total``, ``files_affected``, ``findings``
    (path/name/kind/line/reason), and ``notes`` explaining the blind spots.
    """
    candidates: list[dict] = []
    for path, text in file_contents.items():
        ext = _ext(path)
        if ext not in _PY and ext not in _JSTS:
            continue
        if _is_test(path):
            continue
        defs = _collect_python_defs(path, text) if ext in _PY else _collect_js_defs(path, text)
        for d in defs:
            if _referenced_outside(d["name"], path, file_contents):
                continue
            local = _referenced_locally_only(d["name"], path, text)
            reason = (
                f"public {d['kind']} used only inside its own module; "
                "nothing imports it elsewhere (effectively private)"
                if local
                else f"public {d['kind']} with no references anywhere else in the project"
            )
            candidates.append({**d, "reason": reason})

    candidates.sort(key=lambda c: (c["path"], c["line"]))
    findings = candidates[:_MAX_FINDINGS]
    return {
        "total": len(candidates),
        "files_affected": len({c["path"] for c in candidates}),
        "findings": findings,
        "notes": [
            "Findings are candidates for human review, not proof of dead code: "
            "string references, getattr, dynamic imports, and re-export barrels "
            "are not tracked.",
            "Decorated definitions are skipped because frameworks (FastAPI, "
            "pytest, click, task queues) register them without a visible caller.",
            "A symbol used only inside its own module is flagged as effectively "
            "private, not necessarily dead.",
        ],
    }
