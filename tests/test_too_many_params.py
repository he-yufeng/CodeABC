from backend.services.too_many_params import (
    render_too_many_params_markdown,
    scan_too_many_params,
)


def _func(name: str, params: list[str]) -> str:
    """A function ``name`` with the given parameter signature."""
    return f"def {name}({', '.join(params)}):\n    pass\n"


def test_few_params_is_not_flagged():
    src = _func("f", ["a", "b", "c"])  # 3 params, below default threshold 6
    result = scan_too_many_params({"a.py": src})
    assert result["total"] == 0
    assert result["max_params"] == 3
    assert result["files"] == []


def test_many_params_is_flagged_with_count():
    src = _func("handler", ["a", "b", "c", "d", "e", "f"])  # 6 params
    result = scan_too_many_params({"srv.py": src})
    assert result["total"] == 1
    assert result["max_params"] == 6
    assert result["files"][0] == {"path": "srv.py", "function": "handler", "params": 6}


def test_self_and_cls_are_not_counted():
    # A leading self/cls receiver is not a real parameter, so this method has 6.
    method = _func("m", ["self", "a", "b", "c", "d", "e", "f"])
    result = scan_too_many_params({"m.py": method})
    assert result["files"][0]["params"] == 6
    clsmethod = _func("c", ["cls", "a", "b", "c", "d", "e", "f"])
    assert scan_too_many_params({"c.py": clsmethod})["files"][0]["params"] == 6


def test_varargs_and_kwargs_are_not_counted():
    # 5 named params + *args + **kwargs stays under threshold: the star-args
    # aggregate arguments rather than adding named ones.
    src = _func("f", ["a", "b", "c", "d", "e", "*args", "**kwargs"])
    result = scan_too_many_params({"a.py": src})
    assert result["total"] == 0
    assert result["max_params"] == 5


def test_keyword_only_params_are_counted():
    # 4 positional + 2 keyword-only = 6 named params.
    src = _func("f", ["a", "b", "c", "d", "*", "e", "f"])
    result = scan_too_many_params({"a.py": src})
    assert result["total"] == 1
    assert result["files"][0]["params"] == 6


def test_threshold_is_configurable():
    src = _func("f", ["a", "b", "c", "d"])  # 4 params
    assert scan_too_many_params({"a.py": src})["total"] == 0  # default 6
    assert scan_too_many_params({"a.py": src}, threshold=4)["total"] == 1


def test_results_are_sorted_widest_first():
    files = {
        "a.py": _func("narrow", ["a", "b", "c", "d", "e", "f"]),  # 6
        "b.py": _func("wide", ["a", "b", "c", "d", "e", "f", "g", "h"]),  # 8
    }
    result = scan_too_many_params(files)
    assert [f["function"] for f in result["files"]] == ["wide", "narrow"]


def test_test_files_and_unparseable_are_skipped():
    files = {
        "tests/test_x.py": _func("f", ["a", "b", "c", "d", "e", "f", "g"]),
        "broken.py": "def f(:\n",
    }
    result = scan_too_many_params(files)
    assert result["total"] == 0
    assert result["files"] == []


def test_render_empty_when_nothing_flagged():
    assert render_too_many_params_markdown("proj", None) == ""
    assert render_too_many_params_markdown("proj", {"files": []}) == ""


def test_render_contains_table_and_names():
    data = scan_too_many_params({"srv.py": _func("h", ["a", "b", "c", "d", "e", "f", "g"])})
    md = render_too_many_params_markdown("proj", data)
    assert "proj" in md
    assert "参数过多" in md
    assert "srv.py" in md
    assert "`h`" in md
