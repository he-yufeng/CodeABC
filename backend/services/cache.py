"""Simple SQLite cache for LLM results, keyed by content hash."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import aiosqlite

_DB_PATH = Path.home() / ".codeabc" / "cache.db"
_db: aiosqlite.Connection | None = None

# cache entries expire after 7 days
_TTL_SECONDS = 7 * 24 * 3600


async def init_db():
    global _db
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    _db = await aiosqlite.connect(str(_DB_PATH))
    await _db.execute("""
        CREATE TABLE IF NOT EXISTS cache (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            created_at REAL NOT NULL
        )
    """)
    # projects table: persist project metadata + file contents across restarts
    await _db.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            data TEXT NOT NULL,
            created_at REAL NOT NULL
        )
    """)
    # rate limiting: daily LLM call count per IP
    await _db.execute("""
        CREATE TABLE IF NOT EXISTS rate_limits (
            ip TEXT NOT NULL,
            date TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (ip, date)
        )
    """)
    await _db.commit()


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:24]


async def get(key: str) -> dict | list | None:
    if _db is None:
        return None
    async with _db.execute(
        "SELECT value, created_at FROM cache WHERE key = ?", (key,)
    ) as cursor:
        row = await cursor.fetchone()
    if row is None:
        return None
    value, created_at = row
    if time.time() - created_at > _TTL_SECONDS:
        await _db.execute("DELETE FROM cache WHERE key = ?", (key,))
        await _db.commit()
        return None
    return json.loads(value)


async def put(key: str, value: dict | list):
    if _db is None:
        return
    data = json.dumps(value, ensure_ascii=False)
    await _db.execute(
        "INSERT OR REPLACE INTO cache (key, value, created_at) VALUES (?, ?, ?)",
        (key, data, time.time()),
    )
    await _db.commit()


async def save_project(project_id: str, data: dict):
    """Persist project data (metadata + file contents) to SQLite."""
    if _db is None:
        return
    payload = json.dumps(data, ensure_ascii=False)
    await _db.execute(
        "INSERT OR REPLACE INTO projects (id, data, created_at) VALUES (?, ?, ?)",
        (project_id, payload, time.time()),
    )
    await _db.commit()


_DAILY_LIMIT = 20


async def check_rate_limit(ip: str) -> tuple[bool, int]:
    """Check if IP is within daily free limit.

    Returns (allowed, remaining).
    """
    if _db is None:
        return True, _DAILY_LIMIT

    today = time.strftime("%Y-%m-%d")
    async with _db.execute(
        "SELECT count FROM rate_limits WHERE ip = ? AND date = ?", (ip, today)
    ) as cursor:
        row = await cursor.fetchone()

    current = row[0] if row else 0
    remaining = max(0, _DAILY_LIMIT - current)
    return current < _DAILY_LIMIT, remaining


async def increment_rate_limit(ip: str):
    """Bump the daily usage counter for an IP."""
    if _db is None:
        return
    today = time.strftime("%Y-%m-%d")
    await _db.execute(
        """INSERT INTO rate_limits (ip, date, count) VALUES (?, ?, 1)
           ON CONFLICT (ip, date) DO UPDATE SET count = count + 1""",
        (ip, today),
    )
    await _db.commit()


async def load_project(project_id: str) -> dict | None:
    """Load project data from SQLite. Returns None if not found or expired."""
    if _db is None:
        return None
    async with _db.execute(
        "SELECT data, created_at FROM projects WHERE id = ?", (project_id,)
    ) as cursor:
        row = await cursor.fetchone()
    if row is None:
        return None
    data, created_at = row
    if time.time() - created_at > _TTL_SECONDS:
        await _db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        await _db.commit()
        return None
    return json.loads(data)
