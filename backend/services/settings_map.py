"""Tunable-settings map — the values baked into the code you might want to change.

The env-var surface answers "what do I set *outside* the code before it runs".
This answers the opposite question: "what is set *inside* the code that I might
want to tweak". Almost every project hard-codes a handful of knobs — a retry
count, a timeout, a default model name, a page size, a feature flag — as
module-level constants. For a non-programmer those uppercase lines are the
closest thing to a settings panel the project has, but they are scattered across
files and easy to miss.

This collects them straight from the source CodeABC already loaded — no LLM,
nothing to install — by recognising the two ways a constant is conventionally
declared with a *literal* value:

  Python   ``MAX_RETRIES = 3`` / ``DEFAULT_MODEL: str = "gpt-5"`` (module level)
  JS/TS    ``const PAGE_SIZE = 20`` / ``export const DEBUG = false`` (top level)

Only ``UPPER_SNAKE_CASE`` names assigned a literal scalar or simple literal
collection are kept — that is the universal "this is a constant" convention, and
the literal test cleanly drops type aliases (``Vector = list[float]``) and
computed values (``TIMEOUT = BASE * 2``), which are not knobs a reader can just
edit.

:func:`find_tunable_settings` is pure over the file contents, so it is
unit-testable with plain strings and needs no repository.

Limitations (kept honest on purpose):

  * Module/top level only. A constant defined inside a function or class body is
    local to that scope and not a project-wide knob, so it is skipped.
  * Literal values only. ``RETRIES = int(os.getenv("RETRIES", 3))`` is reported
    by the env-var map instead; here only the bare literal forms are caught.
  * Names must be ``UPPER_SNAKE_CASE``. Lower-case module globals are too easily
    ordinary state to flag as settings safely.
  * A file that does not parse as Python is skipped for the AST pass; the JS/TS
    pass is a conservative line-anchored match and ignores indented constants.
"""

from __future__ import annotations

import ast
import re

_PY_SUFFIX = ".py"
_JS_SUFFIXES = (".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs")

# A constant name: all-caps, digits and underscores, at least two chars so a
# lone loop variable like ``N`` is not mistaken for a setting.
_CONST_NAME = re.compile(r"^[A-Z][A-Z0-9_]*[A-Z0-9]$")

# Top-level JS/TS const with a literal scalar RHS. Anchored at line start (after
# optional ``export``) so indented constants inside functions are ignored.
_JS_CONST = re.compile(
    r"""^(?:export\s+)?const\s+
        ([A-Z][A-Z0-9_]*[A-Z0-9])      # NAME (UPPER_SNAKE)
        \s*(?::[^=]+?)?\s*=\s*          # optional : type   =
        (.+?)\s*;?\s*$                  # the value, up to an optional ;
    """,
    re.MULTILINE | re.VERBOSE,
)

# A bare JS literal we are willing to report: number, quoted string, boolean.
_JS_NUMBER = re.compile(r"^-?\d[\d_]*(?:\.\d+)?(?:[eE][+-]?\d+)?$")
_JS_STRING = re.compile(r"""^(['"`])(.*)\1$""", re.DOTALL)


def _is_const_name(name: str) -> bool:
    return bool(_CONST_NAME.match(name))


def _kind_of(value: object) -> str:
    # bool first: it is a subclass of int.
    if isinstance(value, bool):
        return "flag"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "text"
    if isinstance(value, (list, tuple, set)):
        return "list"
    if isinstance(value, dict):
        return "mapping"
    return "other"


def _truncate(text: str, width: int = 60) -> str:
    return text if len(text) <= width else text[: width - 3] + "..."


def _render_py_value(value: object) -> str:
    if isinstance(value, str):
        return '"' + _truncate(value) + '"'
    return _truncate(repr(value))


def _py_constants(content: str) -> list[dict]:
    """Module-level UPPER_SNAKE constants assigned a literal, in source order."""
    try:
        tree = ast.parse(content)
    except (SyntaxError, ValueError):
        return []

    found: list[dict] = []
    # Module body only — nested scopes are not project-wide settings.
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            targets = stmt.targets
            value_node = stmt.value
        elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
            targets = [stmt.target]
            value_node = stmt.value
        else:
            continue

        # A single simple name target only (skip ``A = B = 1`` and tuple unpack).
        if len(targets) != 1 or not isinstance(targets[0], ast.Name):
            continue
        name = targets[0].id
        if not _is_const_name(name):
            continue

        try:
            value = ast.literal_eval(value_node)
        except (ValueError, SyntaxError, TypeError):
            # Not a pure literal: type alias, computed value, call — not a knob.
            continue
        if value is None:
            continue  # a None sentinel is not a value a reader tweaks

        found.append(
            {
                "name": name,
                "kind": _kind_of(value),
                "value": _render_py_value(value),
                "line": stmt.lineno,
            }
        )
    return found


def _js_constants(content: str) -> list[dict]:
    """Top-level UPPER_SNAKE consts assigned a literal scalar, in source order."""
    found: list[dict] = []
    for match in _JS_CONST.finditer(content):
        name, raw = match.group(1), match.group(2).strip()
        # Drop a trailing comment on the same line.
        raw = re.split(r"\s+//", raw, maxsplit=1)[0].strip().rstrip(";").strip()

        if _JS_NUMBER.match(raw):
            kind, value = "number", raw
        elif raw in ("true", "false"):
            kind, value = "flag", raw
        else:
            string = _JS_STRING.match(raw)
            if not string or "${" in raw:
                # Objects, arrays, calls, template interpolation: not a scalar knob.
                continue
            kind, value = "text", '"' + _truncate(string.group(2)) + '"'

        line = content.count("\n", 0, match.start()) + 1
        found.append({"name": name, "kind": kind, "value": value, "line": line})
    return found


def find_tunable_settings(file_contents: dict[str, str], *, limit: int = 50) -> dict:
    """Collect the literal UPPER_SNAKE constants a project hard-codes.

    Args:
        file_contents: mapping of path to file text (as CodeABC already read it).
        limit: how many settings to return in the sorted list.

    Returns ``{"total", "kinds", "settings"}`` where each setting is
    ``{"name", "kind", "value", "path", "line"}`` and ``kind`` is one of
    ``number`` / ``text`` / ``flag`` / ``list`` / ``mapping``.
    """
    seen: set[tuple[str, str, int]] = set()
    settings: list[dict] = []

    for path, content in file_contents.items():
        if not content:
            continue
        if path.endswith(_PY_SUFFIX):
            entries = _py_constants(content)
        elif path.endswith(_JS_SUFFIXES):
            entries = _js_constants(content)
        else:
            continue

        for entry in entries:
            key = (path, entry["name"], entry["line"])
            if key in seen:
                continue
            seen.add(key)
            settings.append({**entry, "path": path})

    settings.sort(key=lambda s: (s["path"], s["line"]))
    kinds = sorted({s["kind"] for s in settings})
    return {"total": len(settings), "kinds": kinds, "settings": settings[:limit]}


_KIND_LABEL = {
    "number": "数字",
    "text": "文本",
    "flag": "开关",
    "list": "列表",
    "mapping": "映射",
    "other": "其它",
}


def render_settings_markdown(project_name: str, data: dict | None) -> str:
    """Render the tunable-settings map as Markdown, or ``""`` if none were found."""
    settings = (data or {}).get("settings") or []
    if not settings:
        return ""

    lines = [
        f"# {project_name} — 能改哪些值（可调设置）",
        "",
        "> 环境变量是“在代码外面要设置什么”，这里是“代码里面写死、你可能想改的值”——"
        "作者用全大写常量声明的重试次数、超时、默认模型、开关之类。"
        "改它们通常不用读懂整段代码，但请改前看清它在哪、是什么类型。",
        "",
    ]
    current_path = None
    for setting in settings:
        if setting["path"] != current_path:
            current_path = setting["path"]
            lines.append(f"## `{current_path}`")
        label = _KIND_LABEL.get(setting["kind"], setting["kind"])
        lines.append(
            f"- `{setting['name']}` = {setting['value']}  （{label}，第 {setting['line']} 行）"
        )
    return "\n".join(lines).rstrip() + "\n"
