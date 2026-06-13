"""Scan a project directory and collect file info for LLM analysis."""

from __future__ import annotations

import logging
import os
from fnmatch import fnmatch
from pathlib import Path

logger = logging.getLogger(__name__)

# dirs we never want to look at
_SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    ".idea", ".vscode", ".next", "dist", "build", ".tox", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", "egg-info",
}

# binary / non-text extensions
_SKIP_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg", ".webp",
    ".mp3", ".mp4", ".wav", ".avi", ".mov", ".mkv",
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
    ".exe", ".dll", ".so", ".dylib", ".bin", ".dat",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".pyc", ".pyo", ".class", ".o", ".obj",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".db", ".sqlite", ".sqlite3",
    ".lock",  # package-lock.json etc are huge and useless
}

_GENERATED_NAME_SUFFIXES = (
    ".min.js",
    ".min.css",
    ".bundle.js",
    ".bundle.css",
    ".chunk.js",
    ".chunk.css",
)

_ENV_EXAMPLE_FILES = {
    ".env.example",
    ".env.sample",
    ".env.template",
    ".env.defaults",
}

_SENSITIVE_FILENAMES = {
    ".npmrc",
    ".pypirc",
    ".netrc",
    "credentials.json",
    "secrets.json",
    "service-account.json",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
}

_SENSITIVE_DIRS = {
    ".aws",
    ".azure",
    ".gcloud",
    ".gnupg",
    ".ssh",
}

_SENSITIVE_NAME_PATTERNS = (
    "*api_key*",
    "*api-key*",
    "*apikey*",
    "*credential*",
    "*secret*",
    "*access_token*",
    "*auth_token*",
    "*refresh_token*",
)

_SENSITIVE_EXTS = {
    ".key",
    ".pem",
    ".p12",
    ".pfx",
}

# max file size to read (100 KB)
_MAX_FILE_SIZE = 100 * 1024

# how many lines to keep per file for overview context
_PREVIEW_LINES = 80

# hard cap on number of files we'll process
_MAX_FILES = 500

# map extensions -> human readable language name
_LANG_MAP = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".jsx": "jsx", ".tsx": "tsx", ".html": "html", ".css": "css",
    ".json": "json", ".yaml": "yaml", ".yml": "yaml",
    ".md": "markdown", ".txt": "text", ".sh": "shell",
    ".go": "go", ".rs": "rust", ".java": "java",
    ".c": "c", ".cpp": "cpp", ".h": "c", ".hpp": "cpp",
    ".rb": "ruby", ".php": "php", ".r": "r", ".R": "r",
    ".do": "stata", ".sql": "sql", ".toml": "toml",
    ".cfg": "ini", ".ini": "ini", ".env": "text",
    ".swift": "swift", ".kt": "kotlin", ".scala": "scala",
    ".lua": "lua", ".dart": "dart", ".vue": "vue",
    ".svelte": "svelte", ".zig": "zig", ".nim": "nim",
}

# config files that should be read in full (they help LLM understand the project)
_CONFIG_FILES = {
    "requirements.txt", "setup.py", "setup.cfg", "pyproject.toml",
    "package.json", "Cargo.toml", "go.mod", "Makefile", "Dockerfile",
    "docker-compose.yml", "docker-compose.yaml",
    ".env.example", "config.py", "config.yaml", "config.json",
    "README.md", "README.rst", "README.txt", "README",
}


def _has_generated_name(path: str | Path) -> bool:
    name = Path(path).name.lower()
    return name.endswith(_GENERATED_NAME_SUFFIXES)


def _looks_sensitive_path(path: str | Path) -> bool:
    p = Path(path)
    parts = [part.lower() for part in p.parts]
    name = p.name.lower()

    if any(part in _SENSITIVE_DIRS for part in parts):
        return True
    if name.startswith(".env") and name not in _ENV_EXAMPLE_FILES:
        return True
    if name in _SENSITIVE_FILENAMES:
        return True
    if p.suffix.lower() in _SENSITIVE_EXTS:
        return True
    return any(fnmatch(name, pattern) for pattern in _SENSITIVE_NAME_PATTERNS)


def _looks_like_generated_bundle(text: str, language: str) -> bool:
    if language not in {"javascript", "typescript", "jsx", "tsx", "css"}:
        return False

    lines = text.splitlines()
    if not lines:
        return False

    longest = max(len(line.strip()) for line in lines)
    avg = sum(len(line.strip()) for line in lines) / len(lines)
    return longest > 2000 or (len(lines) <= 5 and avg > 500)


def _is_binary(data: bytes) -> bool:
    """Quick check: if there's a null byte in the first 1024 bytes, it's binary."""
    return b"\x00" in data[:1024]


def _detect_language(path: str) -> str:
    ext = Path(path).suffix.lower()
    return _LANG_MAP.get(ext, "unknown")


def _is_safe_path(rel_path: str) -> bool:
    """Reject paths that try to escape the project root."""
    normalized = os.path.normpath(rel_path)
    return not normalized.startswith("..") and not os.path.isabs(normalized)


def _read_gitignore_patterns(root: Path) -> list[str]:
    gitignore = root / ".gitignore"
    if not gitignore.exists():
        return []
    try:
        lines = gitignore.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]


def _matches_gitignore(rel_path: str, is_dir: bool, raw_pattern: str) -> bool:
    pattern = raw_pattern.strip().replace("\\", "/")
    if not pattern or pattern.startswith("!"):
        return False

    directory_only = pattern.endswith("/")
    anchored = pattern.startswith("/")
    pattern = pattern.strip("/")
    if not pattern:
        return False

    if directory_only:
        return (
            rel_path == pattern
            or rel_path.startswith(pattern + "/")
            or (not anchored and f"/{pattern}/" in f"/{rel_path}/")
        )

    if anchored or "/" in pattern:
        return fnmatch(rel_path, pattern) or (not anchored and fnmatch(rel_path, f"*/{pattern}"))

    parts = rel_path.split("/")
    if is_dir:
        return any(fnmatch(part, pattern) for part in parts)
    return fnmatch(parts[-1], pattern) or any(fnmatch(part, pattern) for part in parts[:-1])


def _is_gitignored(root: Path, path: Path, is_dir: bool, patterns: list[str]) -> bool:
    try:
        rel_path = path.relative_to(root).as_posix()
    except ValueError:
        return False

    ignored = False
    for raw in patterns:
        negated = raw.startswith("!")
        pattern = raw[1:] if negated else raw
        if _matches_gitignore(rel_path, is_dir, pattern):
            ignored = not negated
    return ignored


def scan_directory(root: str | Path) -> list[dict]:
    """Walk a project directory and return file metadata + previews.

    Returns list of dicts:
        {"path": relative_path, "size": bytes, "language": str, "preview": str}
    """
    root = Path(root).resolve()
    results = []
    gitignore_patterns = _read_gitignore_patterns(root)

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(dirpath)
        # prune skipped dirs in-place so os.walk won't descend into them
        dirnames[:] = [
            d
            for d in dirnames
            if d not in _SKIP_DIRS
            and not d.endswith(".egg-info")
            and not _is_gitignored(root, current / d, is_dir=True, patterns=gitignore_patterns)
        ]

        for fname in filenames:
            if len(results) >= _MAX_FILES:
                logger.info("Hit file limit (%d), stopping scan", _MAX_FILES)
                break

            full = Path(dirpath) / fname
            rel = str(full.relative_to(root))

            # skip symlinks to prevent escaping the project root
            if full.is_symlink():
                continue
            if _looks_sensitive_path(rel):
                continue
            if _is_gitignored(root, full, is_dir=False, patterns=gitignore_patterns):
                continue

            # skip by extension
            if full.suffix.lower() in _SKIP_EXTS or _has_generated_name(full):
                continue

            # skip oversized files
            try:
                size = full.stat().st_size
            except OSError:
                continue
            if size > _MAX_FILE_SIZE:
                continue
            if size == 0:
                continue

            # try reading
            try:
                raw = full.read_bytes()
            except OSError:
                continue

            if _is_binary(raw):
                continue

            try:
                text = raw.decode("utf-8", errors="replace")
            except Exception:
                continue

            lang = _detect_language(rel)
            if _looks_like_generated_bundle(text, lang):
                continue

            # config files get full content, others get preview
            is_config = fname in _CONFIG_FILES
            if is_config:
                preview = text
            else:
                lines = text.splitlines()
                preview = "\n".join(lines[:_PREVIEW_LINES])

            results.append({
                "path": rel,
                "size": size,
                "language": lang,
                "preview": preview,
            })

        if len(results) >= _MAX_FILES:
            break

    # sort: config/readme first, then by path
    def sort_key(f):
        name = Path(f["path"]).name
        if name in _CONFIG_FILES:
            return (0, f["path"])
        return (1, f["path"])

    results.sort(key=sort_key)
    return results


def scan_uploaded_files(files: list[dict]) -> list[dict]:
    """Process files uploaded from frontend (already have path + content).

    Input: [{"path": str, "content": str}]
    Output: same format as scan_directory
    """
    results = []
    for f in files:
        if len(results) >= _MAX_FILES:
            break

        path = f["path"]
        content = f["content"]

        # reject suspicious paths
        if not _is_safe_path(path):
            logger.warning("Skipping unsafe path: %s", path)
            continue
        if _looks_sensitive_path(path):
            continue

        ext = Path(path).suffix.lower()
        if ext in _SKIP_EXTS or _has_generated_name(path):
            continue

        # skip oversized content
        if len(content) > _MAX_FILE_SIZE:
            continue

        lang = _detect_language(path)
        if _looks_like_generated_bundle(content, lang):
            continue

        fname = Path(path).name
        is_config = fname in _CONFIG_FILES

        if is_config:
            preview = content
        else:
            lines = content.splitlines()
            preview = "\n".join(lines[:_PREVIEW_LINES])

        results.append({
            "path": path,
            "size": len(content.encode()),
            "language": lang,
            "preview": preview,
        })

    def sort_key(f):
        name = Path(f["path"]).name
        if name in _CONFIG_FILES:
            return (0, f["path"])
        return (1, f["path"])

    results.sort(key=sort_key)
    return results
