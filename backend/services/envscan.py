"""Environment-variable surface: what a project needs configured to run.

One of the first questions a newcomer has is "what do I have to set up before
this will run?". Most of that answer lives in the environment variables the code
reads. This collects them from the source CodeABC already loaded — which names
are read, whether they are required (the code crashes if they are missing) or
optional (a default is supplied) — so a reader gets a setup checklist without
hunting through the codebase.

:func:`scan_env_vars` is pure: it matches the common read patterns
(``os.environ["X"]``, ``os.getenv("X"[, default])``, ``os.environ.get(...)`` and
JS ``process.env.X``) over the file contents, so it is unit-testable with plain
strings and needs no repository. A name read at least once via ``os.environ["X"]``
(which raises when the variable is unset) is *required*; a name only ever read
with a graceful fallback (``getenv`` / ``.get`` / ``process.env``) is *optional*.
"""

from __future__ import annotations

import re

# Required reads: os.environ["X"] / os.environ['X'] — a missing key raises.
_REQUIRED_RE = re.compile(r"""os\.environ\[\s*['"](\w+)['"]\s*\]""")
# Optional reads: os.getenv("X"...) / os.environ.get("X"...) — a default may follow.
_OPTIONAL_RE = re.compile(r"""os\.(?:getenv|environ\.get)\(\s*['"](\w+)['"]\s*(,)?""")
# JS: process.env.X / process.env["X"] — always optional (undefined if unset).
_JS_RE = re.compile(r"""process\.env(?:\.(\w+)|\[\s*['"](\w+)['"]\s*\])""")


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
