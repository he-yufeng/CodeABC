"""Scan a project directory and collect file info for LLM analysis."""

from __future__ import annotations

import logging
import os
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


def scan_directory(root: str | Path) -> list[dict]:
    """Walk a project directory and return file metadata + previews.

    Returns list of dicts:
        {"path": relative_path, "size": bytes, "language": str, "preview": str}
    """
    root = Path(root).resolve()
    results = []

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        # prune skipped dirs in-place so os.walk won't descend into them
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS
                       and not d.endswith(".egg-info")]

        for fname in filenames:
            if len(results) >= _MAX_FILES:
                logger.info("Hit file limit (%d), stopping scan", _MAX_FILES)
                break

            full = Path(dirpath) / fname
            rel = str(full.relative_to(root))

            # skip symlinks to prevent escaping the project root
            if full.is_symlink():
                continue

            # skip by extension
            if full.suffix.lower() in _SKIP_EXTS:
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

        ext = Path(path).suffix.lower()
        if ext in _SKIP_EXTS:
            continue

        # skip oversized content
        if len(content) > _MAX_FILE_SIZE:
            continue

        lang = _detect_language(path)
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
