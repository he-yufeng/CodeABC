"""Environment-variable surface: what a project needs configured to run.

One of the first questions a newcomer has is "what do I have to set up before
this will run?". Most of that answer lives in the environment variables the code
reads. This collects them from the source CodeABC already loaded — which names
are read, whether they are required (the code crashes if they are missing) or
optional (a default is supplied) — so a reader gets a setup checklist without
hunting through the codebase.

:func:`scan_env_vars` is pure: it matches the common read patterns over the file
contents, so it is unit-testable with plain strings and needs no repository:

- stdlib ``os.environ["X"]`` (required — raises when unset), ``os.getenv("X")`` /
  ``os.environ.get("X")`` (optional — a default may follow),
- JS ``process.env.X`` (optional),
- Go ``os.Getenv("X")`` / ``os.LookupEnv("X")`` (optional — return "" / a found
  flag rather than panicking) and Rust ``env::var("X")`` (required when
  ``.unwrap()`` / ``.expect(...)`` panics on an unset value, optional otherwise),
- the env-loader libraries many Django/Flask projects use instead of the
  stdlib: ``python-decouple`` (``config("X")``) and ``environs`` /
  ``django-environ`` (``env("X")`` / ``env.str("X")`` / ``env.int(...)`` …).

A name is *required* if it is ever read without a default (``os.environ["X"]``, or
a bare ``config("X")`` / ``env("X")`` — both raise when the variable is unset) and
*optional* if every read supplies a fallback.
"""

from __future__ import annotations

import re

# Required reads: os.environ["X"] / os.environ['X'] — a missing key raises.
_REQUIRED_RE = re.compile(r"""os\.environ\[\s*['"](\w+)['"]\s*\]""")
# Optional reads: os.getenv("X"...) / os.environ.get("X"...) — a default may follow.
# os.environ.setdefault("X", ...) always supplies a fallback, so it is optional too.
_OPTIONAL_RE = re.compile(
    r"""os\.(?:getenv|environ\.get|environ\.setdefault)\(\s*['"](\w+)['"]\s*(,)?"""
)
# JS: process.env.X / process.env["X"] — always optional (undefined if unset).
_JS_RE = re.compile(r"""process\.env(?:\.(\w+)|\[\s*['"](\w+)['"]\s*\])""")
# python-decouple: config("X") / config("X", default=...). A bare read raises
# UndefinedValueError when the var is unset, so config("X") with no default is
# required; a default arg (trailing comma) makes it optional. The lookbehind
# avoids matching attribute calls like ``app.config(...)``.
_DECOUPLE_RE = re.compile(r"""(?<![\w.])config\(\s*['"](\w+)['"]\s*(,)?""")
# environs / django-environ: env("X"), env.str("X"), env.int(...), env.bool(...),
# etc. Same rule as decouple — a bare read raises when the var is unset, a
# default arg makes it optional. ``os.getenv`` / ``os.environ`` never match here
# because the char before this ``env`` is a word char / dot.
_ENVIRONS_RE = re.compile(
    r"""(?<![\w.])env(?:\.(?:str|int|bool|float|list|json|url|path|dict|log_level))?"""
    r"""\(\s*['"](\w+)['"]\s*(,)?"""
)
# Go: os.Getenv("X") returns "" when the variable is unset and os.LookupEnv("X")
# returns (value, ok); both are graceful, so the variable is optional.
_GO_RE = re.compile(r"""os\.(?:Getenv|LookupEnv)\(\s*['"](\w+)['"]""")
# Rust: env::var("X") / std::env::var("X") (and the *_os variants) return a
# ``Result``. A trailing ``.unwrap()`` / ``.expect(...)`` panics when the variable
# is unset (required); ``.unwrap_or(...)`` or any other handling is graceful
# (optional).
_RUST_RE = re.compile(
    r"""(?:std::)?env::var(?:_os)?\(\s*['"](\w+)['"]\s*\)\s*(\.(?:unwrap|expect)\s*\()?"""
)


def scan_env_vars(file_contents: dict[str, str], *, limit: int = 40) -> dict:
    """Collect environment variables read across the project's source.

    Args:
        file_contents: mapping of path to file text (as CodeABC already read it).
        limit: how many variables to return in the ranked list.

    Returns ``{"total", "required", "vars"}`` where ``vars`` is every variable
    name with its read count and whether it is required (read with no default
    anywhere), and ``required`` is just the names of the required ones.
    """
    # name -> {"count": int, "required": bool, "first": (path, line)}
    found: dict[str, dict] = {}

    def _record(name: str, required: bool, path: str, line_no: int) -> None:
        entry = found.get(name)
        if entry is None:
            found[name] = {"count": 1, "required": required, "first": (path, line_no)}
            return
        entry["count"] += 1
        # Required wins: if any read is ``os.environ["X"]`` (raises when unset),
        # the variable must be set regardless of graceful reads elsewhere.
        entry["required"] = entry["required"] or required

    for path, content in file_contents.items():
        if not content:
            continue
        for line_no, line in enumerate(content.splitlines(), start=1):
            for m in _REQUIRED_RE.finditer(line):
                _record(m.group(1), True, path, line_no)
            for m in _OPTIONAL_RE.finditer(line):
                _record(m.group(1), False, path, line_no)
            for m in _JS_RE.finditer(line):
                _record(m.group(1) or m.group(2), False, path, line_no)
            # decouple/environs: required unless a default arg (trailing comma) follows.
            for m in _DECOUPLE_RE.finditer(line):
                _record(m.group(1), m.group(2) is None, path, line_no)
            for m in _ENVIRONS_RE.finditer(line):
                _record(m.group(1), m.group(2) is None, path, line_no)
            for m in _GO_RE.finditer(line):
                _record(m.group(1), False, path, line_no)
            # Rust: required when the read is unwrap()/expect()-ed (panics if unset).
            for m in _RUST_RE.finditer(line):
                _record(m.group(1), m.group(2) is not None, path, line_no)

    vars_list = [
        {
            "name": name,
            "count": info["count"],
            "required": info["required"],
            "path": info["first"][0],
            "line": info["first"][1],
        }
        for name, info in found.items()
    ]
    # Required first, then by how widely the name is read, then alphabetical.
    vars_list.sort(key=lambda v: (not v["required"], -v["count"], v["name"]))

    required = [v["name"] for v in vars_list if v["required"]]

    return {
        "total": len(vars_list),
        "required": required,
        "vars": vars_list[:limit],
    }


def render_env_markdown(project_name: str, env_data: dict | None) -> str:
    """Render the environment-variable surface as Markdown, or ``""`` if none."""
    data = env_data or {}
    vars_list = data.get("vars") or []
    if not vars_list:
        return ""

    total = data.get("total", 0)
    required = data.get("required") or []
    lines = [
        f"# {project_name} — 环境变量",
        "",
        f"> 代码里读取的环境变量共 {total} 个，是“想跑起来要先配什么”的清单。"
        "标 **必填** 的没有默认值，缺了会直接报错。",
        "",
    ]

    if required:
        lines.append(f"## 必填（缺了会报错）：{len(required)} 个")
        lines.append("")
        lines.extend(
            f"- `{v['name']}` — 在 `{v['path']}` 等 {v['count']} 处读取，必须配置。"
            for v in vars_list
            if v["required"]
        )
        lines.append("")

    optional = [v for v in vars_list if not v["required"]]
    if optional:
        lines.append("## 可选（有默认值）")
        lines.append("")
        lines.extend(f"- `{v['name']}` — {v['count']} 处读取，不配会用默认值。" for v in optional)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


_DOC_BASENAMES = (
    ".env.example",
    ".env.sample",
    ".env.template",
    ".env.defaults",
)


def _is_doc_candidate(path: str) -> bool:
    """Whether a file is a place a newcomer would look for env configuration."""
    lower = path.lower()
    base = lower.rsplit("/", 1)[-1]
    if base in _DOC_BASENAMES or base.startswith("readme"):
        return True
    if base.endswith(".md") and (
        "/" not in lower or lower.startswith(("docs/", "doc/", ".github/"))
    ):
        return True
    return False


def find_undocumented_env_vars(scan: dict, file_contents: dict[str, str]) -> list[str]:
    """Names of env vars that no documentation file mentions.

    ``.env.example`` and the README are where a newcomer learns what to
    configure; a variable the code reads but nobody writes down is a setup
    landmine, doubly so when it is required. Matching is a whole-word search
    over every documentation candidate, so ``HOST`` does not count as
    documented just because ``DB_HOST`` appears. Pure over the scan result and
    the file texts, so it is unit-testable with plain dicts.
    """
    doc_text = "\n".join(
        content for path, content in file_contents.items() if _is_doc_candidate(path)
    )
    undocumented = []
    for var in scan.get("vars", []):
        name = var.get("name")
        if not name:
            continue
        if not re.search(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])", doc_text):
            undocumented.append(name)
    return undocumented
