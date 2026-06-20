"""Tests for the test-coverage map (which code files have tests)."""

from __future__ import annotations

from backend.services import coverage


def _f(path, preview="", language="python"):
    return {"path": path, "language": language, "preview": preview}


def test_import_based_coverage():
    # test file imports scanner -> scanner counts as covered; util is not.
    files = [
        _f("backend/scanner.py"),
        _f("backend/util.py"),
        _f("tests/test_scanner.py", "from backend.scanner import scan"),
    ]
    result = coverage.assess_test_coverage(files)
    assert result["total_source_files"] == 2  # scanner + util, not the test
    assert result["tested_files"] == 1
    assert result["test_files"] == 1
    untested = {u["path"] for u in result["untested_core"]}
    assert "backend/util.py" in untested
    assert "backend/scanner.py" not in untested


def test_name_based_coverage_without_import():
    # no import edge, but test_scanner.py <-> scanner.py by convention.
    files = [
        _f("backend/scanner.py"),
        _f("tests/test_scanner.py", "# exercises behaviour indirectly"),
    ]
    result = coverage.assess_test_coverage(files)
    assert result["tested_files"] == 1
    assert result["coverage_percent"] == 100


def test_js_spec_naming():
    files = [
        _f("src/parser.ts", language="typescript"),
        _f("src/parser.test.ts", "import { parse } from './parser'", "typescript"),
        _f("src/format.ts", language="typescript"),
    ]
    result = coverage.assess_test_coverage(files)
    covered = result["total_source_files"] - result["untested_files"]
    assert covered == 1  # parser covered, format not
    assert any(u["path"] == "src/format.ts" for u in result["untested_core"])


def test_untested_core_ranked_by_fan_in():
    # core.py is imported by three files but has no test -> top of untested_core.
    files = [
        _f("core.py"),
        _f("leaf.py"),
        _f("a.py", "import core"),
        _f("b.py", "import core"),
        _f("c.py", "import core"),
    ]
    result = coverage.assess_test_coverage(files)
    assert result["test_files"] == 0
    assert result["untested_core"][0]["path"] == "core.py"
    assert result["untested_core"][0]["fan_in"] == 3
    # most-depended-on untested file ranks above the isolated leaf
    paths = [u["path"] for u in result["untested_core"]]
    assert paths.index("core.py") < paths.index("leaf.py")


def test_no_tests_note():
    files = [_f("a.py"), _f("b.py")]
    result = coverage.assess_test_coverage(files)
    assert result["coverage_percent"] == 0
    assert any("没有" in n and "测试" in n for n in result["notes"])


def test_packaging_files_excluded_from_source():
    # __init__.py / conftest.py are not counted as untested source noise.
    files = [
        _f("pkg/__init__.py"),
        _f("pkg/real.py"),
        _f("tests/conftest.py"),
        _f("tests/test_real.py", "from pkg.real import thing"),
    ]
    result = coverage.assess_test_coverage(files)
    assert result["total_source_files"] == 1  # only pkg/real.py
    assert result["coverage_percent"] == 100


def test_render_markdown():
    assert coverage.render_coverage_markdown("demo", None) == ""
    assert coverage.render_coverage_markdown("demo", {"total_source_files": 0}) == ""
    files = [_f("core.py"), _f("a.py", "import core")]
    result = coverage.assess_test_coverage(files)
    md = coverage.render_coverage_markdown("demo", result)
    assert "测试覆盖" in md
    assert "`core.py`" in md
    assert md.endswith("\n")


def test_limit_caps_untested_core():
    files = [_f(f"m{i}.py") for i in range(20)]
    result = coverage.assess_test_coverage(files, limit=5)
    assert len(result["untested_core"]) == 5
    assert result["untested_files"] == 20
