"""External dependencies: the third-party libraries a project pulls in.

The reading map and entry points tell a newcomer what to read and how to run the
code; this answers another practical first question — "what does this project
depend on, and what would I need to install?". It reads the dependency manifests
CodeABC already loaded (``requirements*.txt``, ``pyproject.toml``, ``setup.cfg``,
``Pipfile``, ``package.json``) and lists the declared third-party packages,
marking each as runtime, development, or optional and noting which manifest it
came from.

This is deliberately distinct from the internal import/package graph: it is about
the *external* libraries the project installs, not how its own modules reference
each other. :func:`scan_dependencies` is pure over the file contents, so it is
unit-testable with plain strings and needs no repository or network.
"""

from __future__ import annotations

import json
import re

_RUNTIME = "runtime"
_DEV = "dev"
_OPTIONAL = "optional"

# Lower rank wins when the same package shows up in more than one role.
_KIND_RANK = {_RUNTIME: 0, _DEV: 1, _OPTIONAL: 2}
_KIND_LABEL = {_RUNTIME: "运行依赖", _DEV: "开发依赖", _OPTIONAL: "可选依赖"}

# A quoted string inside a TOML/JSON array.
_QUOTED_RE = re.compile(r"""['"]([^'"]+)['"]""")
# A `name = <value>` table entry (poetry / Pipfile style), one per line.
_TABLE_ENTRY_RE = re.compile(r"""(?m)^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*=\s*(.+?)\s*$""")
# A requirements filename: requirements.txt, requirements-dev.txt, ...
_REQUIREMENTS_RE = re.compile(r"requirements.*\.txt", re.I)


def _section(content: str, header: str) -> str:
    """Text of a TOML/INI ``[header]`` section, until the next top-level header."""
    start = content.find(f"[{header}]")
    if start == -1:
        return ""
    rest = content[start + len(header) + 2 :]
    end = re.search(r"(?m)^\s*\[", rest)
    return rest[: end.start()] if end else rest


def _array_body(text: str, key: str) -> str:
    """Raw body of a TOML ``key = [ ... ]`` array.

    Walks to the matching ``]`` while tracking nesting and ignoring any brackets
    that appear *inside* quoted strings — so an extras marker like
    ``"requests[security]>=2"`` does not terminate the array early.
    """
    m = re.search(rf"(?m)^\s*{re.escape(key)}\s*=\s*\[", text)
    if not m:
        return ""
    depth, quote, out, i = 1, "", [], m.end()
    while i < len(text) and depth > 0:
        c = text[i]
        if quote:
            if c == quote:
                quote = ""
            out.append(c)
        elif c in "'\"":
            quote = c
            out.append(c)
        elif c == "[":
            depth += 1
            out.append(c)
        elif c == "]":
            depth -= 1
            if depth:
                out.append(c)
        else:
            out.append(c)
        i += 1
    return "".join(out)


def _req_name_version(spec: str) -> tuple[str, str] | None:
    """Parse a requirement string into ``(name, version_spec)``.

    Returns ``None`` for anything that is not a package: blanks, comments, pip
    options (``-r``, ``--index-url``), or a bare VCS/URL requirement with no
    resolvable name.
    """
    spec = spec.split("#", 1)[0].strip()
    if not spec or spec.startswith("-"):
        return None
    spec = spec.split(";", 1)[0].strip()  # drop environment markers
    m = re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", spec)
    if not m:
        return None
    name = m.group(0)
    rest = re.sub(r"^\s*\[[^\]]*\]", "", spec[m.end() :]).strip()  # drop extras
    if " @ " in rest or "://" in rest:  # "pkg @ git+https://..." has no clean version
        rest = ""
    return name, rest


def _from_requirements(content: str, kind: str) -> list[tuple[str, str, str]]:
    deps = []
    for line in content.splitlines():
        parsed = _req_name_version(line)
        if parsed:
            deps.append((parsed[0], parsed[1], kind))
    return deps


def _from_pyproject(content: str) -> list[tuple[str, str, str]]:
    deps: list[tuple[str, str, str]] = []
    # PEP 621: [project] dependencies = [...] and [project.optional-dependencies].
    for spec in _QUOTED_RE.findall(_array_body(content, "dependencies")):
        parsed = _req_name_version(spec)
        if parsed:
            deps.append((parsed[0], parsed[1], _RUNTIME))
    for spec in _QUOTED_RE.findall(_section(content, "project.optional-dependencies")):
        parsed = _req_name_version(spec)
        if parsed:
            deps.append((parsed[0], parsed[1], _OPTIONAL))
    # Poetry: [tool.poetry.dependencies] uses `name = "^1.0"` table entries.
    for header, kind in (
        ("tool.poetry.dependencies", _RUNTIME),
        ("tool.poetry.dev-dependencies", _DEV),
        ("tool.poetry.group.dev.dependencies", _DEV),
    ):
        for name, raw in _TABLE_ENTRY_RE.findall(_section(content, header)):
            if name == "python":  # the interpreter constraint, not a dependency
                continue
            version = next(iter(_QUOTED_RE.findall(raw)), "")
            deps.append((name, "" if version == "*" else version, kind))
    return deps


def _from_setup_cfg(content: str) -> list[tuple[str, str, str]]:
    block = _section(content, "options")
    m = re.search(r"(?m)^install_requires\s*=(.*)$", block)
    if not m:
        return []
    lines = block[m.start() :].splitlines()
    items = [lines[0].split("=", 1)[1].strip()]
    for line in lines[1:]:
        if not line.strip():
            continue
        if line[0] in " \t":  # indented continuation line
            items.append(line.strip())
        else:  # a new dedented key ends the install_requires block
            break
    deps = []
    for item in items:
        parsed = _req_name_version(item)
        if parsed:
            deps.append((parsed[0], parsed[1], _RUNTIME))
    return deps


def _from_pipfile(content: str) -> list[tuple[str, str, str]]:
    deps = []
    for header, kind in (("packages", _RUNTIME), ("dev-packages", _DEV)):
        for name, raw in _TABLE_ENTRY_RE.findall(_section(content, header)):
            version = next(iter(_QUOTED_RE.findall(raw)), "")
            deps.append((name, "" if version == "*" else version, kind))
    return deps


def _from_package_json(content: str) -> list[tuple[str, str, str]]:
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return []
    deps = []
    for field, kind in (
        ("dependencies", _RUNTIME),
        ("devDependencies", _DEV),
        ("optionalDependencies", _OPTIONAL),
        ("peerDependencies", _OPTIONAL),
    ):
        block = data.get(field)
        if isinstance(block, dict):
            deps.extend((str(name), str(ver), kind) for name, ver in block.items())
    return deps


def scan_dependencies(file_contents: dict[str, str], *, limit: int = 200) -> dict:
    """Collect the project's declared third-party dependencies from its manifests.

    Args:
        file_contents: mapping of path to file text (as CodeABC already read it).
        limit: how many dependencies to return in the ranked list.

    Returns ``{"total", "dependencies", "manifests"}`` where each dependency is
    ``{"name", "version", "kind", "manifest"}`` and ``kind`` is one of
    ``runtime``, ``dev`` or ``optional``. A package seen in several roles is kept
    once at its strongest role (runtime over dev over optional).
    """
    best: dict[str, dict] = {}
    manifests: list[str] = []

    def _add(name: str, version: str, kind: str, manifest: str) -> None:
        key = name.lower()
        existing = best.get(key)
        if existing is None or _KIND_RANK[kind] < _KIND_RANK[existing["kind"]]:
            best[key] = {
                "name": name,
                "version": version.strip(),
                "kind": kind,
                "manifest": manifest,
            }

    for path, content in file_contents.items():
        if not content:
            continue
        name = path.replace("\\", "/").rsplit("/", 1)[-1]
        if _REQUIREMENTS_RE.fullmatch(name):
            kind = _DEV if re.search(r"dev|test", name, re.I) else _RUNTIME
            collected = _from_requirements(content, kind)
        elif name == "pyproject.toml":
            collected = _from_pyproject(content)
        elif name == "setup.cfg":
            collected = _from_setup_cfg(content)
        elif name == "Pipfile":
            collected = _from_pipfile(content)
        elif name == "package.json":
            collected = _from_package_json(content)
        else:
            continue
        if collected:
            manifests.append(name)
            for dep_name, version, kind in collected:
                _add(dep_name, version, kind, name)

    deps = sorted(best.values(), key=lambda d: (_KIND_RANK[d["kind"]], d["name"].lower()))
    return {
        "total": len(deps),
        "dependencies": deps[:limit],
        "manifests": sorted(set(manifests)),
    }


def render_dependencies_markdown(project_name: str, data: dict | None) -> str:
    """Render the external dependencies as Markdown, or ``""`` if none were found."""
    deps = (data or {}).get("dependencies") or []
    if not deps:
        return ""
    manifests = (data or {}).get("manifests") or []
    source = "、".join(f"`{m}`" for m in manifests)
    lines = [
        f"# {project_name} — 外部依赖清单（第三方库）",
        "",
        "> 这个项目要装哪些第三方库才能跑。运行依赖是跑起来必须的，开发依赖只在改代码/跑测试时用，"
        f"可选依赖按需安装。来源：{source}。",
        "",
    ]
    for kind in (_RUNTIME, _DEV, _OPTIONAL):
        group = [d for d in deps if d["kind"] == kind]
        if not group:
            continue
        lines.append(f"## {_KIND_LABEL[kind]}（{len(group)}）")
        lines.append("")
        for d in group:
            version = f" `{d['version']}`" if d["version"] else ""
            lines.append(f"- **{d['name']}**{version} — 来自 `{d['manifest']}`")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
