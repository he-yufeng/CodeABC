from backend.services.typing_coverage import (
    render_typing_coverage_markdown,
    scan_typing_coverage,
)


def test_fully_typed_file_is_not_flagged():
    src = "def add(a: int, b: int) -> int:\n    return a + b\n"
    result = scan_typing_coverage({"good.py": src})
    assert result["files"] == []
    assert result["total_symbols"] == 1
    assert result["typed"] == 1
    assert result["coverage"] == 1.0


def test_counts_public_functions_and_methods_excludes_private_and_dunders():
    src = (
        "def parse(path: str) -> str:\n"
        "    return path\n"
        "class Loader:\n"
        "    def run(self, x):\n"  # public method, param x untyped
        "        return x\n"
        "    def _private(self):\n"  # excluded (leading underscore)
        "        return 2\n"
        "    def __init__(self):\n"  # excluded (dunder)
        "        self.x = 1\n"
    )
    result = scan_typing_coverage({"loader.py": src})
    # public surface: parse (typed) + Loader.run (untyped); the class itself is not counted.
    assert result["total_symbols"] == 2
    assert result["typed"] == 1
    assert result["files"][0]["path"] == "loader.py"
    assert "Loader.run" in result["files"][0]["missing"]
    assert "parse" not in result["files"][0]["missing"]


def test_missing_return_annotation_is_untyped():
    result = scan_typing_coverage({"m.py": "def f(a: int):\n    return a\n"})
    assert result["typed"] == 0
    assert result["total_symbols"] == 1


def test_missing_param_annotation_is_untyped():
    result = scan_typing_coverage({"m.py": "def f(a, b: int) -> int:\n    return b\n"})
    assert result["typed"] == 0


def test_self_and_cls_are_exempt():
    src = (
        "class C:\n"
        "    def method(self) -> int:\n"
        "        return 1\n"
        "    def maker(cls, x: int) -> int:\n"
        "        return x\n"
    )
    result = scan_typing_coverage({"c.py": src})
    assert result["typed"] == 2
    assert result["total_symbols"] == 2
    assert result["files"] == []


def test_varargs_and_kwargs_must_be_annotated():
    ok = "def f(*args: int, **kwargs: str) -> None:\n    return None\n"
    assert scan_typing_coverage({"ok.py": ok})["typed"] == 1
    bad = "def f(*args, **kwargs) -> None:\n    return None\n"
    assert scan_typing_coverage({"bad.py": bad})["typed"] == 0


def test_no_params_needs_only_return_annotation():
    assert scan_typing_coverage({"a.py": "def f() -> int:\n    return 1\n"})["typed"] == 1
    assert scan_typing_coverage({"b.py": "def f():\n    return 1\n"})["typed"] == 0


def test_tests_and_non_python_and_unparseable_are_skipped():
    files = {
        "tests/test_x.py": "def helper(a):\n    return a\n",
        "readme.md": "def f(a):\n    return a\n",
        "broken.py": "def f(:\n",
        "conftest.py": "def fixture():\n    pass\n",
    }
    result = scan_typing_coverage(files)
    assert result["total_symbols"] == 0
    assert result["coverage"] == 1.0


def test_worst_file_first_and_totals():
    a = "".join(f"def f{i}(x):\n    return x\n" for i in range(3))  # 3 untyped
    b = "def g(x: int) -> int:\n    return x\ndef h(x):\n    return x\n"  # 1 typed, 1 untyped
    result = scan_typing_coverage({"a.py": a, "b.py": b})
    assert result["files"][0]["path"] == "a.py"  # more un-typed functions ranks first
    assert result["files"][0]["symbols"] == 3
    assert result["files"][0]["typed"] == 0
    assert result["total_symbols"] == 5
    assert result["typed"] == 1


def test_render_empty_when_nothing_to_report():
    assert render_typing_coverage_markdown("proj", None) == ""
    assert render_typing_coverage_markdown("proj", {"total_symbols": 0}) == ""


def test_render_contains_coverage_and_files():
    data = scan_typing_coverage({"m.py": "def f(a):\n    return a\n"})
    md = render_typing_coverage_markdown("proj", data)
    assert "proj" in md
    assert "类型注解覆盖率" in md
    assert "m.py" in md
    assert "0%" in md
