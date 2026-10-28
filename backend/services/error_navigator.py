"""Map pasted stack traces to source already scanned into a project.

The parser never opens a path named by the log. It only resolves suffixes against
the project's in-memory ``file_contents`` and returns short, read-only excerpts.
"""

from __future__ import annotations

import re

from backend.services import filenames

_MAX_LOCATIONS = 20
_SOURCE_EXTENSIONS = (
    "py",
    "pyw",
    "js",
    "jsx",
    "ts",
    "tsx",
    "mjs",
    "cjs",
    "go",
    "java",
    "rb",
    "rs",
    "c",
    "cc",
    "cpp",
    "h",
    "hpp",
    "cs",
    "php",
)
_EXTENSION_ALTERNATION = "|".join(_SOURCE_EXTENSIONS)
_PYTHON_FRAME = re.compile(r'\bFile "(?P<path>[^"]+)", line (?P<line>\d+)')
_GENERIC_FRAME = re.compile(
    r"(?P<path>(?:file://)?(?:[A-Za-z]:[\\/]|/|\.{0,2}[\\/])?"
    rf"[^\s()\"']+?\.(?:{_EXTENSION_ALTERNATION}))"
    r":(?P<line>\d+)(?::(?P<column>\d+))?",
    re.IGNORECASE,
)


def _normalize_path(raw_path: str) -> str:
    path = raw_path.strip().strip("\"'")
    if path.startswith("file://"):
        path = path[7:]
    path = path.replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path


def _resolve_path(raw_path: str, scanned_paths: dict[str, str]) -> str | None:
    normalized = _normalize_path(raw_path)
    if normalized in scanned_paths:
        return scanned_paths[normalized]

    suffix_matches = [
        scanned_path
        for normalized_path, scanned_path in scanned_paths.items()
        if normalized.endswith("/" + normalized_path)
    ]
    if suffix_matches:
        longest = max(map(len, suffix_matches))
        longest_matches = [path for path in suffix_matches if len(path) == longest]
        if len(longest_matches) == 1:
            return longest_matches[0]

    basename = normalized.rsplit("/", 1)[-1].lower()
    basename_matches = [
        scanned_path
        for scanned_path in scanned_paths.values()
        if scanned_path.rsplit("/", 1)[-1].lower() == basename
    ]
    if len(basename_matches) == 1:
        return basename_matches[0]
    return None


def _candidates(log: str) -> list[tuple[str, int, int | None]]:
    found: list[tuple[str, int, int | None]] = []
    seen: set[tuple[str, int, int | None]] = set()
    for pattern in (_PYTHON_FRAME, _GENERIC_FRAME):
        for match in pattern.finditer(log):
            raw_path = match.group("path")
            if "://" in raw_path and not raw_path.startswith("file://"):
                continue
            candidate = (
                _normalize_path(raw_path),
                int(match.group("line")),
                int(match.group("column")) if match.groupdict().get("column") else None,
            )
            if candidate not in seen:
                seen.add(candidate)
                found.append(candidate)
    return found


def _excerpt(content: str, line: int) -> str:
    lines = content.splitlines()
    start = max(1, line - 2)
    end = min(len(lines), line + 2)
    return "\n".join(f"{number:>4} | {lines[number - 1]}" for number in range(start, end + 1))


def locate_error(log: str, file_contents: dict[str, str]) -> dict:
    """Return source locations in log order, deduplicated and capped at 20."""
    scanned_paths = {_normalize_path(path): path for path in file_contents if _normalize_path(path)}
    locations = []
    unresolved = 0
    seen_locations: set[tuple[str, int]] = set()
    truncated = False

    for raw_path, line, column in _candidates(log):
        path = _resolve_path(raw_path, scanned_paths)
        if path is None or (path, line) in seen_locations:
            if path is None:
                unresolved += 1
            continue
        content = file_contents[path]
        if line < 1 or line > len(content.splitlines()):
            unresolved += 1
            continue

        seen_locations.add((path, line))
        if len(locations) >= _MAX_LOCATIONS:
            truncated = True
            continue
        purpose = filenames.explain_path(path) or {}
        locations.append(
            {
                "path": path,
                "line": line,
                "column": column,
                "kind": purpose.get("kind", ""),
                "purpose": purpose.get("explanation", ""),
                "excerpt": _excerpt(content, line),
            }
        )

    return {"locations": locations, "unresolved": unresolved, "truncated": truncated}
