"""Config-file surface: the settings files a project ships and what you can change.

Three questions cover "how is this configured", and CodeABC answers each from a
different angle:

- :mod:`envscan` — "what must I set *outside* the code before it runs" (env vars).
- :mod:`settings_map` — "what constants are baked *inside* the code" (module-level
  ``UPPER_SNAKE`` literals).
- this module — "what config *files* does the project ship, and what top-level
  settings can I change in them" — the ``config.yaml`` / ``settings.toml`` /
  ``*.ini`` a newcomer opens to configure the project without touching code.

:func:`find_config_files` is pure over the file contents: it recognises config
files by name/extension and extracts their top-level keys (YAML/JSON) or
``[section]`` headers (TOML/INI) with the conventional syntax — no YAML/TOML
parser, nothing to install — so it is unit-testable with plain strings and needs
no repository.

Recognised as config (so a random ``data.json`` fixture is not mistaken for one):

- a config-ish **basename** — ``config`` / ``settings`` / ``conf`` / ``options`` /
  ``appsettings`` (any extension below), or a well-known name like ``pyproject.toml``,
  ``tox.ini``, ``setup.cfg``;
- with a config **extension** — ``.yaml`` / ``.yml`` / ``.toml`` / ``.ini`` /
  ``.cfg`` / ``.conf`` / ``.json`` / ``.properties``.

Top-level settings only (kept honest): nested keys and array items are not
descended into — this is a surface map ("here is the config file and its top-level
knobs"), not a full parse.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

# A config extension is necessary but not sufficient — pair it with a config-ish
# name so ordinary data/fixture files in those formats are not swept in.
_CONFIG_EXTS = {".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".json", ".properties"}
# Basenames (sans extension) that mark a file as project configuration.
_CONFIG_STEMS = {"config", "settings", "conf", "options", "appsettings", "application"}
# Well-known config files whose name doesn't contain a config stem. Kept to
# files with a config extension so their format is unambiguous; extension-less
# dotfiles (.editorconfig / .prettierrc) are left out since their syntax isn't
# implied by the name.
_WELL_KNOWN = {
    "pyproject.toml",
    "setup.cfg",
    "tox.ini",
}

# YAML/properties: a top-level `key:` / `key =` at column 0 (no leading space, so
# nested mapping keys and list items are skipped).
_YAML_KEY_RE = re.compile(r"^([A-Za-z_][\w-]*)\s*:", re.MULTILINE)
_PROPS_KEY_RE = re.compile(r"^([A-Za-z_][\w.-]*)\s*[=:]", re.MULTILINE)
# TOML/INI: `[section]` / `[section.sub]` headers at column 0.
_SECTION_RE = re.compile(r"^\[([^\]]+)\]", re.MULTILINE)
# TOML/INI: a bare `key =` at column 0 (top of file, before any section).
_TOML_KEY_RE = re.compile(r"^([A-Za-z_][\w.-]*)\s*=", re.MULTILINE)
# JSON: keys nested exactly one level (two-space or tab indent) — the top-level
# object's members. Deeper keys carry more indent and are skipped.
_JSON_TOP_KEY_RE = re.compile(r'^(?:  |\t)"([^"]+)"\s*:', re.MULTILINE)


def _kind_for(name: str) -> str | None:
    """Classify a path as a config file, returning its format kind or ``None``."""
    p = PurePosixPath(name)
    base = p.name.lower()
    ext = p.suffix.lower()
    if ext not in _CONFIG_EXTS:
        return None
    stem = p.stem.lower()
    # A config extension alone isn't enough; require a config-ish name so a data
    # ``users.json`` or a CI ``matrix.yaml`` fixture isn't treated as settings.
    if base not in _WELL_KNOWN and stem not in _CONFIG_STEMS:
        # Allow `<name>.config.json` / `<name>.conf.yaml` style compound names.
        if ".config" not in stem and ".conf" not in stem:
            return None
    if ext in (".yaml", ".yml"):
        return "yaml"
    if ext == ".toml":
        return "toml"
    if ext in (".ini", ".cfg", ".conf"):
        return "ini"
    if ext == ".json":
        return "json"
    if ext == ".properties":
        return "properties"
    return None


def _dedupe(items: list[str], limit: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out[:limit]


def _extract(kind: str, content: str, *, per_file_limit: int) -> tuple[list[str], list[str]]:
    """Return ``(sections, keys)`` for one config file's top-level surface."""
    sections: list[str] = []
    keys: list[str] = []
    if kind == "yaml":
        keys = _dedupe(_YAML_KEY_RE.findall(content), per_file_limit)
    elif kind == "properties":
        keys = _dedupe(_PROPS_KEY_RE.findall(content), per_file_limit)
    elif kind in ("toml", "ini"):
        sections = _dedupe(_SECTION_RE.findall(content), per_file_limit)
        # Keys above the first section header are the file's top-level settings.
        head = content.split("\n[", 1)[0]
        keys = _dedupe(_TOML_KEY_RE.findall(head), per_file_limit)
    elif kind == "json":
        keys = _dedupe(_JSON_TOP_KEY_RE.findall(content), per_file_limit)
    return sections, keys


def find_config_files(
    file_contents: dict[str, str], *, limit: int = 40, per_file_limit: int = 30
) -> dict:
    """Collect the project's shipped config files and their top-level settings.

    Args:
        file_contents: mapping of path to file text (as CodeABC already read it).
        limit: how many config files to return in the ranked list.
        per_file_limit: how many sections/keys to keep per file.

    Returns ``{"total", "kinds", "files"}`` where each file has its ``kind``
    (yaml/toml/ini/json/properties), its top-level ``sections`` (TOML/INI) and
    ``keys``, and a ``setting_count`` for ranking.
    """
    files: list[dict] = []
    for path, content in file_contents.items():
        if not content:
            continue
        kind = _kind_for(path)
        if kind is None:
            continue
        sections, keys = _extract(kind, content, per_file_limit=per_file_limit)
        # A recognised config file with no readable top-level settings is still
        # worth surfacing (the reader now knows the file exists), but rank it low.
        files.append(
            {
                "path": path,
                "kind": kind,
                "sections": sections,
                "keys": keys,
                "setting_count": len(sections) + len(keys),
            }
        )

    # Richest, most-central config first, then alphabetical for stability.
    files.sort(key=lambda f: (-f["setting_count"], f["path"]))
    kinds = sorted({f["kind"] for f in files})
    return {"total": len(files), "kinds": kinds, "files": files[:limit]}


def render_config_files_markdown(project_name: str, data: dict | None) -> str:
    """Render the config-file surface as Markdown, or ``""`` if none."""
    d = data or {}
    files = d.get("files") or []
    if not files:
        return ""

    lines = [
        f"# {project_name} — 配置文件",
        "",
        f"> 项目自带 {d.get('total', len(files))} 个配置文件，是"
        "“不改代码就能调整项目行为”的地方。下面列出每个文件里你可以改的顶层设置。",
        "",
    ]
    for f in files:
        lines.append(f"## `{f['path']}` — {f['kind'].upper()}")
        if f["sections"]:
            joined = "、".join(f"`{s}`" for s in f["sections"])
            lines.append(f"- 分区（section）：{joined}")
        if f["keys"]:
            joined = "、".join(f"`{k}`" for k in f["keys"])
            lines.append(f"- 顶层设置：{joined}")
        if not f["sections"] and not f["keys"]:
            lines.append("- （识别为配置文件，但没解析出顶层设置——可能是嵌套结构，打开看看。）")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
