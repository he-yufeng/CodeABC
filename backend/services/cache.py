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
