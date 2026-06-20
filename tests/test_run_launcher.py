"""Tests for the one-command launcher's readiness polling.

run.py lives at the repo root (it's a script, not part of the backend package),
so add the root to sys.path before importing it.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import run  # noqa: E402  # pyright: ignore[reportMissingImports]


def test_wait_until_returns_true_once_probe_succeeds():
    # Fails the first two checks, then the "server" comes up.
    calls = {"n": 0}

    def probe():
        calls["n"] += 1
        return calls["n"] >= 3

    assert run.wait_until(probe, timeout=1, interval=0.001) is True
    assert calls["n"] == 3


def test_wait_until_returns_false_on_timeout():
    # Server never answers; we should give up rather than block forever.
    assert run.wait_until(lambda: False, timeout=0.05, interval=0.001) is False


def test_wait_until_does_not_poll_again_after_success():
    # A probe that is already ready should be called exactly once.
    calls = {"n": 0}

    def probe():
        calls["n"] += 1
        return True

    assert run.wait_until(probe, timeout=1, interval=0.001) is True
    assert calls["n"] == 1
