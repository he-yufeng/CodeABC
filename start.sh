#!/usr/bin/env bash
# One-click launcher for CodeABC on macOS / Linux.
cd "$(dirname "$0")" || exit 1
exec python3 run.py
