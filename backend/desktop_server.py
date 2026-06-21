"""Entry point for the bundled desktop backend (Tauri sidecar).

The desktop app ships this as a standalone binary (built with PyInstaller) and
spawns it on startup, so a user who just wants the native window doesn't have to
start a Python server themselves. It runs the same FastAPI app on a loopback
port; the desktop webview talks to it over 127.0.0.1.

The built frontend isn't next to this binary, so ``backend.app`` skips mounting
the SPA and serves the API only — the Tauri shell already serves the UI.
"""

from __future__ import annotations

import os
import sys
import threading

import uvicorn

from backend.app import app


def _exit_when_parent_dies() -> None:
    """Shut down when our stdin closes — i.e. when the desktop app dies.

    Tauri wires our stdin to the parent process. When that process goes away
    (a normal quit, but also a crash or a force-kill that never runs the app's
    cleanup), the pipe hits EOF and we exit, so we never linger as an orphaned
    server holding the port. Run standalone from a terminal, stdin stays open
    and this simply waits.
    """
    try:
        sys.stdin.read()
    except Exception:
        pass
    os._exit(0)


def main() -> None:
    threading.Thread(target=_exit_when_parent_dies, daemon=True).start()
    port = int(os.getenv("CODEABC_PORT", "8000"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
