"""Tests for the SQLite cache: LLM-result caching, project persistence, rate limiting."""

from __future__ import annotations

import asyncio


def _with_cache(tmp_path, monkeypatch, scenario):
    """Run an async scenario against a fresh, isolated temp-file cache DB.

    The whole connection lifecycle (open, use, close) stays inside one event
    loop, so the single aiosqlite connection is never shared across loops.
    """
    from backend.services import cache

    monkeypatch.setattr(cache, "_DB_PATH", tmp_path / "cache.db")

    async def main():
        await cache.init_db()
        try:
            return await scenario(cache)
        finally:
            if cache._db is not None:
                await cache._db.close()
                cache._db = None

    return asyncio.run(main())


def test_put_get_roundtrip_preserves_unicode(tmp_path, monkeypatch):
    async def scenario(cache):
        await cache.put("k", {"summary": "茅台是一只股票", "n": 3})
        return await cache.get("k")

    assert _with_cache(tmp_path, monkeypatch, scenario) == {"summary": "茅台是一只股票", "n": 3}


def test_get_missing_key_returns_none(tmp_path, monkeypatch):
    async def scenario(cache):
        return await cache.get("never-written")

    assert _with_cache(tmp_path, monkeypatch, scenario) is None


def test_put_replaces_existing_value(tmp_path, monkeypatch):
    async def scenario(cache):
        await cache.put("k", {"v": 1})
        await cache.put("k", {"v": 2})
        return await cache.get("k")

    assert _with_cache(tmp_path, monkeypatch, scenario) == {"v": 2}


def test_expired_entry_is_evicted_on_get(tmp_path, monkeypatch):
    async def scenario(cache):
        await cache.put("k", {"v": 1})
        # force every entry to count as expired, then read it back
        monkeypatch.setattr(cache, "_TTL_SECONDS", -1)
        value = await cache.get("k")
        # the stale row should be deleted, not merely hidden
        async with cache._db.execute("SELECT COUNT(*) FROM cache") as cur:
            (remaining,) = await cur.fetchone()
        return value, remaining

    value, remaining = _with_cache(tmp_path, monkeypatch, scenario)
    assert value is None
    assert remaining == 0


def test_content_hash_is_deterministic_and_truncated():
    from backend.services import cache

    h1 = cache.content_hash("def foo(): pass")
    h2 = cache.content_hash("def foo(): pass")
    h3 = cache.content_hash("def bar(): pass")
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 24
    assert all(c in "0123456789abcdef" for c in h1)


def test_rate_limit_blocks_at_daily_limit(tmp_path, monkeypatch):
    from backend.services import cache

    monkeypatch.setattr(cache, "_DAILY_LIMIT", 3)

    async def scenario(cache):
        ip = "1.2.3.4"
        first = await cache.check_rate_limit(ip)
        await cache.increment_rate_limit(ip)
        await cache.increment_rate_limit(ip)
        mid = await cache.check_rate_limit(ip)
        await cache.increment_rate_limit(ip)
        last = await cache.check_rate_limit(ip)
        return first, mid, last

    first, mid, last = _with_cache(tmp_path, monkeypatch, scenario)
    assert first == (True, 3)  # nothing used yet
    assert mid == (True, 1)  # 2 of 3 used
    assert last == (False, 0)  # limit reached -> blocked


def test_rate_limit_is_per_ip(tmp_path, monkeypatch):
    from backend.services import cache

    monkeypatch.setattr(cache, "_DAILY_LIMIT", 1)

    async def scenario(cache):
        await cache.increment_rate_limit("10.0.0.1")
        blocked = await cache.check_rate_limit("10.0.0.1")
        fresh = await cache.check_rate_limit("10.0.0.2")
        return blocked, fresh

    blocked, fresh = _with_cache(tmp_path, monkeypatch, scenario)
    assert blocked == (False, 0)  # this IP spent its single call
    assert fresh == (True, 1)  # a different IP is unaffected


def test_project_save_load_roundtrip(tmp_path, monkeypatch):
    async def scenario(cache):
        await cache.save_project("proj1", {"name": "演示", "files": [1, 2]})
        return await cache.load_project("proj1"), await cache.load_project("missing")

    found, missing = _with_cache(tmp_path, monkeypatch, scenario)
    assert found == {"name": "演示", "files": [1, 2]}
    assert missing is None


def test_expired_project_is_evicted_on_load(tmp_path, monkeypatch):
    async def scenario(cache):
        await cache.save_project("p", {"x": 1})
        monkeypatch.setattr(cache, "_TTL_SECONDS", -1)
        value = await cache.load_project("p")
        async with cache._db.execute("SELECT COUNT(*) FROM projects") as cur:
            (remaining,) = await cur.fetchone()
        return value, remaining

    value, remaining = _with_cache(tmp_path, monkeypatch, scenario)
    assert value is None
    assert remaining == 0


def test_operations_are_safe_before_init(monkeypatch):
    """Every accessor degrades gracefully when the DB was never initialised."""
    from backend.services import cache

    monkeypatch.setattr(cache, "_db", None)

    async def scenario():
        assert await cache.get("k") is None
        await cache.put("k", {"v": 1})  # no-op, must not raise
        await cache.save_project("p", {"v": 1})  # no-op, must not raise
        assert await cache.load_project("p") is None
        await cache.increment_rate_limit("ip")  # no-op, must not raise
        # storage unavailable -> fail open: allow, with the full quota
        return await cache.check_rate_limit("ip")

    assert asyncio.run(scenario()) == (True, cache._DAILY_LIMIT)
