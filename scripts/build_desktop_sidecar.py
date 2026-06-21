"""Build the bundled backend binary that the desktop app spawns.

The Tauri desktop app ships the FastAPI backend as a sidecar so it's
self-contained — no separate ``python run.py``. This script packages
``backend/desktop_server.py`` into a standalone binary with PyInstaller and
drops it where Tauri expects it (``frontend/src-tauri/binaries/`` with the
Rust target-triple suffix), so ``npm run tauri:build`` can bundle it.

Run it from the repo root in an environment that has the project installed
(``pip install -e .``) plus ``pyinstaller``:

    python scripts/build_desktop_sidecar.py

Build the backend in a clean virtualenv (only the project's own deps), not a
fat data-science env — PyInstaller will otherwise vacuum up everything that's
installed and produce a multi-gigabyte binary.
"""

from __future__ import annotations

import subprocess
import sys
import sysconfig
from pathlib import Path

# Map Python's platform tag to the Rust target triple Tauri appends to the
# sidecar filename. Extend this when building on another OS/arch.
_TRIPLES = {
    "win-amd64": "x86_64-pc-windows-msvc",
    "linux-x86_64": "x86_64-unknown-linux-gnu",
    "macosx-x86_64": "x86_64-apple-darwin",
    "macosx-arm64": "aarch64-apple-darwin",
}


def _target_triple() -> str:
    plat = sysconfig.get_platform()
    for key, triple in _TRIPLES.items():
        if plat.startswith(key):
            return triple
    raise SystemExit(f"unsupported platform {plat!r}; add it to _TRIPLES")


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    triple = _target_triple()
    binaries = root / "frontend" / "src-tauri" / "binaries"
    binaries.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--onefile",
            "--name",
            "codeabc-backend",
            "--distpath",
            str(root / "_pyi_dist"),
            "--workpath",
            str(root / "_pyi_build"),
            "--specpath",
            str(root / "_pyi_build"),
            # litellm + its providers, plus the tiktoken encoding plugin it
            # imports at startup (missing it crashes with "Unknown encoding").
            "--collect-submodules",
            "litellm",
            "--collect-data",
            "litellm",
            "--hidden-import",
            "tiktoken_ext.openai_public",
            "--hidden-import",
            "tiktoken_ext",
            "--copy-metadata",
            "tiktoken",
            "--collect-data",
            "tiktoken",
            # uvicorn loads these lazily, so PyInstaller can't see them.
            "--collect-submodules",
            "uvicorn",
            "--hidden-import",
            "uvicorn.lifespan.on",
            "--hidden-import",
            "uvicorn.protocols.http.auto",
            "--hidden-import",
            "uvicorn.protocols.websockets.auto",
            "--hidden-import",
            "uvicorn.loops.auto",
            str(root / "backend" / "desktop_server.py"),
        ],
        check=True,
    )

    suffix = ".exe" if triple.endswith("windows-msvc") else ""
    built = root / "_pyi_dist" / f"codeabc-backend{suffix}"
    dest = binaries / f"codeabc-backend-{triple}{suffix}"
    dest.write_bytes(built.read_bytes())
    print(f"sidecar ready: {dest}")


if __name__ == "__main__":
    main()
