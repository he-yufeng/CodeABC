from backend.services.long_functions import (
    render_long_functions_markdown,
    scan_long_functions,
)


def _func(name: str, body_lines: int) -> str:
    """A function ``name`` spanning ``1 + body_lines`` physical lines."""
    body = "".join(f"    x{i} = {i}\n" for i in range(body_lines))
    return f"def {name}():\n{body}"


def test_short_function_is_not_flagged():
    src = _func("f", 5)  # 6 lines total, below the default threshold
    result = scan_long_functions({"a.py": src})
    assert result["total"] == 0
    assert result["max_length"] == 6
    assert result["files"] == []


def test_long_function_is_flagged_with_its_line_span():
    src = _func("handler", 59)  # def + 59 body lines = 60 lines
    result = scan_long_functions({"srv.py": src})
    assert result["total"] == 1
    assert result["max_length"] == 60
    assert result["files"][0] == {"path": "srv.py", "function": "handler", "length": 60}


def test_decorators_do_not_count_toward_length():
    # node.lineno points at ``def``, so the two decorator lines above are excluded.
    src = "@deco1\n@deco2\n" + _func("g", 59)  # 60-line body, 2 decorators on top
    result = scan_long_functions({"m.py": src})
    assert result["files"][0]["length"] == 60


def test_nested_helper_is_measured_separately():
    # Both the long inner helper and the (even longer) outer that contains it are
    # over threshold, so each surfaces on its own row.
    src = (
        "def outer():\n"
        + "".join(f"    y{i} = {i}\n" for i in range(2))
        + ("    def inner():\n" + "".join(f"        z{i} = {i}\n" for i in range(60)))
    )
    result = scan_long_functions({"m.py": src})
    names = {f["function"] for f in result["files"]}
    assert "inner" in names
    assert "outer" in names


def test_threshold_is_configurable():
    src = _func("f", 20)  # 21 lines
    assert scan_long_functions({"a.py": src})["total"] == 0  # default threshold 60
    assert scan_long_functions({"a.py": src}, threshold=21)["total"] == 1


def test_results_are_sorted_longest_first():
    files = {"a.py": _func("short_one", 60), "b.py": _func("long_one", 100)}
    result = scan_long_functions(files)
    assert [f["function"] for f in result["files"]] == ["long_one", "short_one"]


def test_test_files_and_unparseable_are_skipped():
    files = {
        "tests/test_x.py": _func("f", 80),
        "broken.py": "def f(:\n",
    }
    result = scan_long_functions(files)
    assert result["total"] == 0
    assert result["files"] == []


def test_render_empty_when_nothing_flagged():
    assert render_long_functions_markdown("proj", None) == ""
    assert render_long_functions_markdown("proj", {"files": []}) == ""


def test_render_contains_table_and_names():
    data = scan_long_functions({"srv.py": _func("h", 70)})
    md = render_long_functions_markdown("proj", data)
    assert "proj" in md
    assert "过长的函数" in md
    assert "srv.py" in md
    assert "`h`" in md
