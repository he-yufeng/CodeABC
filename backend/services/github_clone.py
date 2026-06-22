"""Clone GitHub repositories with safety limits."""

from __future__ import annotations

import asyncio
import hashlib
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse

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


# A bare "owner/repo" shorthand: a GitHub login (alphanumerics + hyphens) and a
# repo name (which may contain dots, underscores, hyphens), nothing else.
_SHORTHAND = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9._-]+$")


def _parse_github_url(url: str) -> tuple[str, str]:
    """Extract (owner, repo) from the many shapes people paste.

    Handles the plain repo URL, a link pointing somewhere *inside* the repo
    (``/tree/main``, ``/blob/...``, ``?tab=stars``, ``#readme`` — what you get by
    copying the browser address bar), the ``.git`` suffix, the ``git@`` SSH form,
    and the bare ``owner/repo`` shorthand. Rejects non-GitHub hosts.
    """
    text = url.strip()

    ssh = re.match(r"^git@github\.com:(.+)$", text, re.IGNORECASE)
    if ssh:
        path = ssh.group(1)
    elif "://" not in text and "github.com" not in text.lower() and _SHORTHAND.match(text):
        path = text
    else:
        parsed = urlparse(text if "://" in text else "https://" + text)
        host = (parsed.hostname or "").lower()
        if host not in ("github.com", "www.github.com"):
            raise ValueError(f"Only GitHub repositories are supported: {url}")
        path = parsed.path

    # A query string or fragment may still ride along in the SSH/shorthand paths.
    path = path.split("?")[0].split("#")[0].strip("/")
    if path.lower().endswith(".git"):
        path = path[:-4]

    parts = [p for p in path.split("/") if p]
    if len(parts) < 2:
        raise ValueError(f"Cannot find owner/repo in: {url}")
    return parts[0], parts[1]


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

    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "clone",
            "--depth",
            "1",
            clone_url,
            str(dest),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        # git isn't installed — the clone path can't work. Say so plainly
        # instead of letting a raw OSError become a 500. (Uploading a folder
        # still works without git.)
        shutil.rmtree(dest, ignore_errors=True)
        raise ValueError(
            "Git isn't installed, so cloning from a URL won't work. "
            "Install Git from https://git-scm.com, or upload the project folder instead."
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
