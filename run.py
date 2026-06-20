#!/usr/bin/env python3
"""One-command launcher for CodeABC.

Gets a non-technical user from "I downloaded this" to a running app in a single
step: it prepares the Python dependencies, builds the web UI the first time,
then starts the server and opens it in the browser. The backend serves the
built UI itself, so there is only one process and one URL to think about.

    python run.py            # any platform
    start.bat                # Windows, double-click
    ./start.sh               # macOS / Linux

Set CODEABC_PORT to use a different port (default 8000).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"
DIST_INDEX = FRONTEND / "dist" / "index.html"
HOST = os.getenv("CODEABC_HOST", "127.0.0.1")
PORT = os.getenv("CODEABC_PORT", "8000")
URL = f"http://{HOST}:{PORT}"
HEALTH_URL = f"{URL}/api/health"


def say(msg: str) -> None:
    print(f"  {msg}", flush=True)


def run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True)


def have(tool: str) -> bool:
    return shutil.which(tool) is not None


def ensure_frontend_built() -> None:
    """Build the web UI once; reuse it on every later run."""
    if DIST_INDEX.is_file():
        return
    npm = shutil.which("npm")
    if not npm:
        sys.exit(
            "\n  Node.js / npm was not found, and the web UI hasn't been built yet.\n"
            "  Install Node 18+ from https://nodejs.org and run this again.\n"
            "  (Node is only needed once, to build the interface.)\n"
        )
    say("Building the web interface - first run only, about a minute...")
    installer = "ci" if (FRONTEND / "package-lock.json").is_file() else "install"
    run([npm, installer], FRONTEND)
    run([npm, "run", "build"], FRONTEND)
    say("Web interface ready.")


def server_command() -> list[str]:
    """Command that starts the server, installing backend deps if needed."""
    uvicorn = ["-m", "uvicorn", "backend.app:app", "--host", HOST, "--port", PORT]
    if have("uv"):
        # uv syncs the dependencies from pyproject/uv.lock on the fly
        return ["uv", "run", "python", *uvicorn]
    # No uv: use a local virtualenv so the system Python is never touched.
    venv = ROOT / ".venv"
    bin_dir = "Scripts" if os.name == "nt" else "bin"
    py = venv / bin_dir / ("python.exe" if os.name == "nt" else "python")
    if not py.is_file():
        say("Setting up a virtual environment (first run only)...")
        run([sys.executable, "-m", "venv", str(venv)], ROOT)
        run([str(py), "-m", "pip", "install", "-q", "--upgrade", "pip"], ROOT)
        say("Installing backend dependencies...")
        run([str(py), "-m", "pip", "install", "-q", "-e", "."], ROOT)
    return [str(py), *uvicorn]


def wait_until(probe: Callable[[], bool], timeout: float, interval: float = 0.5) -> bool:
    """Poll ``probe`` until it returns True or ``timeout`` seconds pass.

    Returns True if the probe ever succeeded, False if it timed out first.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if probe():
            return True
        time.sleep(interval)
    return False


def server_responding() -> bool:
    """True once the backend answers its health check."""
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=1) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError):
        return False


def open_browser_when_ready() -> None:
    # Wait for the server to actually answer before opening the browser. A first
    # run may still be building a virtualenv or installing dependencies, and
    # popping open the page too early would show a "can't connect" error. Give it
    # a generous window for slow first installs, then open anyway as a fallback
    # so the browser always opens eventually.
    wait_until(server_responding, timeout=120)
    try:
        webbrowser.open(URL)
    except Exception:
        pass


def main() -> None:
    print("\n  CodeABC - read any codebase without learning to code")
    print("  " + "-" * 50)
    if not have("uv"):
        say("Tip: installing uv (https://docs.astral.sh/uv/) makes startup faster.")
    ensure_frontend_built()
    threading.Thread(target=open_browser_when_ready, daemon=True).start()
    say(f"CodeABC will open in your browser at {URL} as soon as it's ready.")
    say("Leave this window open while you use it; press Ctrl+C to stop.\n")
    try:
        run(server_command(), ROOT)
    except KeyboardInterrupt:
        say("Stopped. See you next time.")
    except subprocess.CalledProcessError as exc:
        sys.exit(f"\n  Could not start CodeABC (exit {exc.returncode}). See the messages above.\n")


if __name__ == "__main__":
    main()
