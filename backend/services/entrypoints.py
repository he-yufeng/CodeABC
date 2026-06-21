"""Entry points: where a project actually starts running.

The reading map tells a newcomer what to read first to *understand* the code;
this answers the other half of the question — "how do I run it, and where does
execution begin?". It collects the runnable "front doors" from the source
CodeABC already loaded: files with a ``__main__`` guard, the console commands
declared in ``pyproject.toml`` / ``setup.cfg``, the ``bin`` of a ``package.json``,
and a few conventional entry filenames — so a reader doesn't have to guess where
to start the program.

:func:`find_entry_points` is pure over the file contents, so it is unit-testable
with plain strings and needs no repository.
"""

from __future__ import annotations

import json
import re

# `if __name__ == "__main__":` — running the file executes this block.
_MAIN_GUARD_RE = re.compile(r"""^\s*if\s+__name__\s*==\s*['"]__main__['"]\s*:""", re.M)
# A console-script entry inside a [project.scripts]-style table: name = "target".
_SCRIPT_ENTRY_RE = re.compile(r"""^\s*([\w][\w\-.]*)\s*=\s*['"]([^'"]+)['"]""", re.M)

# Conventional entry filenames and what running them usually means. Only used as
# a fallback hint when nothing more explicit points at the file.
_CONVENTIONAL = {
    "__main__.py": "包入口，可用 `python -m <package>` 运行",
    "main.py": "常见的程序主入口",
    "manage.py": "Django 管理命令入口（`python manage.py ...`）",
    "wsgi.py": "WSGI 服务器入口（gunicorn/uwsgi 从这里加载应用）",
    "asgi.py": "ASGI 服务器入口（uvicorn 从这里加载应用）",
    "cli.py": "命令行入口",
    "server.js": "Node 服务器入口",
    "index.js": "Node 程序入口",
}

# Priority for ranking: an explicitly declared command beats a runnable script,
# which beats a by-convention guess.
_KIND_RANK = {"command": 0, "script": 1, "convention": 2}

_SCRIPT_REASON = '直接运行会执行文件里的 `if __name__ == "__main__"` 代码'


def _section(content: str, header: str) -> str:
    """Return the text of a TOML/INI ``[header]`` section (until the next header)."""
    start = content.find(f"[{header}]")
    if start == -1:
        return ""
    rest = content[start + len(header) + 2 :]
    end = re.search(r"^\s*\[", rest, re.M)
    return rest[: end.start()] if end else rest


def _declared_commands(path: str, content: str) -> list[tuple[str, str]]:
    """Console commands declared in pyproject.toml / setup.cfg / package.json."""
    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    commands: list[tuple[str, str]] = []

    if name == "pyproject.toml":
        for header in ("project.scripts", "project.gui-scripts", "tool.poetry.scripts"):
            for cmd, target in _SCRIPT_ENTRY_RE.findall(_section(content, header)):
                commands.append((cmd, target))

    elif name == "setup.cfg":
        # console_scripts live under [options.entry_points] as "cmd = module:fn".
        block = _section(content, "options.entry_points")
        if "console_scripts" in block:
            for cmd, target in _SCRIPT_ENTRY_RE.findall(block):
                if cmd != "console_scripts":
                    commands.append((cmd, target))

    elif name == "package.json":
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            return commands
        bins = data.get("bin")
        if isinstance(bins, str):
            commands.append((str(data.get("name") or "bin"), bins))
        elif isinstance(bins, dict):
            commands.extend((str(k), str(v)) for k, v in bins.items())

    return commands


def find_entry_points(file_contents: dict[str, str], *, limit: int = 40) -> dict:
    """Collect the project's runnable entry points from its source.

    Args:
        file_contents: mapping of path to file text (as CodeABC already read it).
        limit: how many entry points to return in the ranked list.

    Returns ``{"total", "entry_points"}`` where each entry point is
    ``{"path", "kind", "command", "reason"}`` and ``kind`` is one of
    ``command`` (a declared console command), ``script`` (a file with a
    ``__main__`` guard) or ``convention`` (a conventional entry filename).
    """
    # path -> best entry (keep the highest-priority kind seen for a path/command).
    found: dict[tuple[str, str], dict] = {}

    def _add(path: str, kind: str, command: str, reason: str) -> None:
        key = (path, command)
        existing = found.get(key)
        if existing is None or _KIND_RANK[kind] < _KIND_RANK[existing["kind"]]:
            found[key] = {"path": path, "kind": kind, "command": command, "reason": reason}

    for path, content in file_contents.items():
        if not content:
            continue
        name = path.replace("\\", "/").rsplit("/", 1)[-1]

        for cmd, target in _declared_commands(path, content):
            _add(path, "command", cmd, f"命令行命令 `{cmd}`（运行 {target}）")

        if name.endswith(".py") and _MAIN_GUARD_RE.search(content):
            _add(path, "script", f"python {path}", _SCRIPT_REASON)
        elif name in _CONVENTIONAL:
            _add(path, "convention", path, _CONVENTIONAL[name])

    entries = sorted(found.values(), key=lambda e: (_KIND_RANK[e["kind"]], e["path"]))
    return {"total": len(entries), "entry_points": entries[:limit]}


def render_entrypoints_markdown(project_name: str, data: dict | None) -> str:
    """Render the entry points as Markdown, or ``""`` if none were found."""
    entries = (data or {}).get("entry_points") or []
    if not entries:
        return ""

    labels = {
        "command": "命令行命令",
        "script": "可直接运行的脚本",
        "convention": "按惯例的入口文件",
    }
    lines = [
        f"# {project_name} — 怎么跑起来（入口点）",
        "",
        "> 程序从这些“门”开始运行。命令行命令是作者明确声明的，脚本是能直接跑的文件，"
        "其余是按文件名惯例推断的入口。",
        "",
    ]
    for kind in ("command", "script", "convention"):
        group = [e for e in entries if e["kind"] == kind]
        if not group:
            continue
        lines.append(f"## {labels[kind]}")
        lines.append("")
        lines.extend(f"- `{e['command']}` — {e['reason']}" for e in group)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
