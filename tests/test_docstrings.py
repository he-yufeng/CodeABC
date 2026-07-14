from backend.services.docstrings import (
    render_docstring_coverage_markdown,
    scan_docstring_coverage,
)


def test_fully_documented_file_is_not_flagged():
    src = '"""module."""\ndef public_fn():\n    """documented."""\n    return 1\n'
    result = scan_docstring_coverage({"good.py": src})
    assert result["files"] == []
    assert result["total_symbols"] == 1
    assert result["documented"] == 1
    assert result["coverage"] == 1.0


def test_counts_public_symbols_and_excludes_private_and_dunders():
    src = (
        "def parse_manifest(path):\n"
        "    return path\n"
        "class Loader:\n"
        "    def run(self):\n"  # public method, no docstring
        "        return 1\n"
        "    def _private(self):\n"  # excluded (leading underscore)
        "        return 2\n"
        "    def __init__(self):\n"  # excluded (dunder)
        "        self.x = 1\n"
    )
    result = scan_docstring_coverage({"loader.py": src})
    # public surface: parse_manifest, Loader, Loader.run == 3; private/dunder skipped
    assert result["total_symbols"] == 3
    assert result["documented"] == 0
    entry = result["files"][0]
    assert entry["symbols"] == 3
    assert "Loader.run" in entry["missing"]
    assert "Loader._private" not in entry["missing"]
    assert "Loader.__init__" not in entry["missing"]


def test_coverage_fraction_across_files():
    documented = '"""m."""\ndef a():\n    """d."""\n    return 1\n'
    undocumented = "def b():\n    return 2\n"
    result = scan_docstring_coverage({"a.py": documented, "b.py": undocumented})
    # 1 of 2 public symbols documented
    assert result["total_symbols"] == 2
    assert result["documented"] == 1
    assert result["coverage"] == 0.5


def test_ranks_least_documented_first():
    two_missing = "def a():\n    return 1\ndef b():\n    return 2\n"
    one_missing = "def c():\n    return 3\n"
    result = scan_docstring_coverage({"one.py": one_missing, "two.py": two_missing})
    assert [f["path"] for f in result["files"]] == ["two.py", "one.py"]


def test_tests_non_python_and_unparseable_are_skipped():
    files = {
        "tests/test_thing.py": "def test_it():\n    assert True\n",
        "notes.md": "def looks_like_code(): pass",
        "broken.py": "def oops(:\n    pass\n",
        "real.py": "def keep(x):\n    return x\n",
    }
    result = scan_docstring_coverage(files)
    assert [f["path"] for f in result["files"]] == ["real.py"]
    assert result["total_symbols"] == 1


def test_private_only_file_contributes_nothing():
    result = scan_docstring_coverage({"helpers.py": "def _helper():\n    return 1\n"})
    assert result["total_symbols"] == 0
    assert result["coverage"] == 1.0  # nothing to document reads as complete
    assert result["files"] == []


def test_render_markdown_or_empty():
    assert render_docstring_coverage_markdown("x", {"total_symbols": 0}) == ""
    assert render_docstring_coverage_markdown("x", None) == ""
    md = render_docstring_coverage_markdown(
        "Demo", scan_docstring_coverage({"m.py": "def undoc():\n    return 1\n"})
    )
    assert "API 文档覆盖率" in md
    assert "`m.py`" in md
    assert "undoc" in md
