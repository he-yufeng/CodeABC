from backend.services.deep_nesting import (
    render_deep_nesting_markdown,
    scan_deep_nesting,
)


def _deep4(name: str) -> str:
    """A function ``name`` whose control flow nests 4 levels deep (for>if>while>with)."""
    return (
        f"def {name}(xs):\n"
        "    for x in xs:\n"
        "        if x:\n"
        "            while x:\n"
        "                with x:\n"
        "                    x.go()\n"
    )


def test_flat_code_is_not_flagged():
    src = "def f(x):\n    if x:\n        return 1\n    return 0\n"  # depth 1
    result = scan_deep_nesting({"a.py": src})
    assert result["total"] == 0
    assert result["max_depth"] == 1
    assert result["files"] == []


def test_deeply_nested_function_is_flagged():
    src = (
        "def handler(items):\n"
        "    for it in items:\n"  # 1
        "        if it:\n"  # 2
        "            while it.next:\n"  # 3
        "                try:\n"  # 4
        "                    it.step()\n"
        "                except Exception:\n"
        "                    pass\n"
    )
    result = scan_deep_nesting({"srv.py": src})
    assert result["total"] == 1
    assert result["max_depth"] == 4
    assert result["files"][0] == {"path": "srv.py", "function": "handler", "depth": 4}


def test_nested_helper_does_not_inflate_outer_depth():
    # The outer function is shallow (depth 1); the deep nesting lives inside a
    # nested helper, which must be measured on its own, not attributed to outer.
    src = (
        "def outer():\n"
        "    if True:\n"  # outer depth 1
        "        def inner(xs):\n"
        "            for x in xs:\n"  # 1
        "                if x:\n"  # 2
        "                    while x:\n"  # 3
        "                        with x:\n"  # 4
        "                            x.go()\n"
        "        return inner\n"
    )
    result = scan_deep_nesting({"m.py": src})
    names = {f["function"]: f["depth"] for f in result["files"]}
    assert "outer" not in names  # outer is depth 1, below threshold
    assert names.get("inner") == 4


def test_threshold_is_configurable():
    src = "def f(xs):\n    for x in xs:\n        if x:\n            x.go()\n"  # depth 2
    assert scan_deep_nesting({"a.py": src})["total"] == 0  # default threshold 4
    assert scan_deep_nesting({"a.py": src}, threshold=2)["total"] == 1


def test_test_files_and_unparseable_are_skipped():
    files = {
        "tests/test_x.py": _deep4("f"),
        "broken.py": "def f(:\n",
    }
    result = scan_deep_nesting(files)
    assert result["total"] == 0
    assert result["files"] == []


def test_render_empty_when_nothing_flagged():
    assert render_deep_nesting_markdown("proj", None) == ""
    assert render_deep_nesting_markdown("proj", {"files": []}) == ""


def test_render_contains_table_and_names():
    data = scan_deep_nesting({"srv.py": _deep4("h")})
    md = render_deep_nesting_markdown("proj", data)
    assert "proj" in md
    assert "嵌套" in md
    assert "srv.py" in md
    assert "`h`" in md
