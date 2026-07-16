from backend.services.async_surface import (
    render_async_surface_markdown,
    scan_async_surface,
)


def test_sync_only_project_has_no_async_surface():
    result = scan_async_surface({"a.py": "def f():\n    return 1\n"})
    assert result["async_functions"] == 0
    assert result["async_modules"] == 0
    assert result["files"] == []


def test_counts_async_defs_including_nested():
    src = (
        "async def handler():\n"
        "    async def inner():\n"  # nested coroutine still counts
        "        return 1\n"
        "    return await inner()\n"
        "def helper():\n"  # sync
        "    return 2\n"
    )
    result = scan_async_surface({"srv.py": src})
    assert result["async_functions"] == 2  # handler + inner
    assert result["async_modules"] == 1
    assert result["total_functions"] == 3
    assert result["files"][0]["path"] == "srv.py"
    assert result["files"][0]["async_defs"] == 2
    assert result["files"][0]["sync_defs"] == 1


def test_most_async_file_ranks_first():
    a = "async def x():\n    return 1\n"
    b = "async def y():\n    return 1\nasync def z():\n    return 2\n"
    result = scan_async_surface({"a.py": a, "b.py": b})
    assert result["files"][0]["path"] == "b.py"  # 2 coroutines outrank 1
    assert result["async_modules"] == 2
    assert result["async_functions"] == 3


def test_tests_and_non_python_and_unparseable_are_skipped():
    files = {
        "tests/test_x.py": "async def helper():\n    return 1\n",
        "readme.md": "async def f():\n    return 1\n",
        "broken.py": "async def f(:\n",
    }
    result = scan_async_surface(files)
    assert result["async_functions"] == 0
    assert result["files"] == []


def test_render_empty_when_no_coroutines():
    assert render_async_surface_markdown("proj", None) == ""
    assert render_async_surface_markdown("proj", {"async_functions": 0}) == ""


def test_render_contains_counts_and_files():
    data = scan_async_surface({"srv.py": "async def h():\n    return 1\ndef s():\n    return 2\n"})
    md = render_async_surface_markdown("proj", data)
    assert "proj" in md
    assert "异步面" in md
    assert "srv.py" in md
    assert "1 个 async" in md
