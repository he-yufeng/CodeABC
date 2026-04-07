"""Clone GitHub repositories with safety limits."""

from __future__ import annotations

import asyncio
import hashlib
import shutil
import tempfile
from pathlib import Path

# 500 MB max repo size after clone
_MAX_REPO_SIZE_MB = 500
_CLONE_TIMEOUT = 120  # seconds


def _repo_dir_size(path: Path) -> int:
    """Total size in bytes of all files under path."""
    total = 0
    for f in path.rglob("*"):
        if f.is_file():
            total += f.stat().st_size
    return total


def _parse_github_url(url: str) -> tuple[str, str]:
    """Extract owner/repo from a GitHub URL. Returns (owner, repo)."""
    # handle both https://github.com/owner/repo and https://github.com/owner/repo.git
    url = url.rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    parts = url.split("/")
    # find github.com in parts
    try:
        idx = parts.index("github.com")
    except ValueError:
        raise ValueError(f"Not a valid GitHub URL: {url}")
    if len(parts) < idx + 3:
        raise ValueError(f"Cannot parse owner/repo from: {url}")
    return parts[idx + 1], parts[idx + 2]


async def clone_repo(url: str) -> Path:
    """Shallow-clone a GitHub repo and return the local path.

    Raises ValueError if the repo is too large or clone fails.
    The caller is responsible for cleaning up the directory when done.
    """
    owner, repo = _parse_github_url(url)
    url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
    dest = Path(tempfile.gettempdir()) / "codeabc_repos" / f"{owner}_{repo}_{url_hash}"

    # reuse if already cloned
    if dest.exists() and (dest / ".git").exists():
        return dest

    dest.mkdir(parents=True, exist_ok=True)

    # normalize URL to https
    clone_url = f"https://github.com/{owner}/{repo}.git"

    proc = await asyncio.create_subprocess_exec(
        "git", "clone", "--depth", "1", clone_url, str(dest),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=_CLONE_TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        shutil.rmtree(dest, ignore_errors=True)
        raise ValueError(f"Clone timed out after {_CLONE_TIMEOUT}s: {url}")

    if proc.returncode != 0:
        err_msg = stderr.decode(errors="replace").strip()
        shutil.rmtree(dest, ignore_errors=True)
        raise ValueError(f"Git clone failed: {err_msg}")

    # check size
    size_mb = _repo_dir_size(dest) / (1024 * 1024)
    if size_mb > _MAX_REPO_SIZE_MB:
        shutil.rmtree(dest, ignore_errors=True)
        raise ValueError(f"Repo too large ({size_mb:.0f} MB > {_MAX_REPO_SIZE_MB} MB limit)")

    return dest


def cleanup_repo(path: Path) -> None:
    """Remove a cloned repo directory."""
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
