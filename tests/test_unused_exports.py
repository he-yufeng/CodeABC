"""Tests for the unused-exports (candidate dead code) analysis."""

from __future__ import annotations

from backend.services.unused_exports import find_unused_exports


def test_public_function_with_no_references_is_flagged():
    result = find_unused_exports({"a.py": "def helper():\n    return 1\n"})
    assert result["total"] == 1
    f = result["findings"][0]
    assert f["name"] == "helper"
    assert f["kind"] == "function"
    assert "no references" in f["reason"]


def test_referenced_elsewhere_is_alive():
    files = {
        "a.py": "def helper():\n    return 1\n",
        "b.py": "from a import helper\n\nx = helper()\n",
    }
    assert find_unused_exports(files)["total"] == 0


def test_used_only_in_tests_is_alive():
    files = {
        "a.py": "def helper():\n    return 1\n",
        "tests/test_a.py": "from a import helper\n\n\ndef test_x():\n    assert helper() == 1\n",
    }
    assert find_unused_exports(files)["total"] == 0


def test_local_only_use_is_flagged_as_effectively_private():
    src = "def helper():\n    return 1\n\n\ndef public_entry():\n    return helper()\n"
    result = find_unused_exports({"a.py": src})
    names = {f["name"] for f in result["findings"]}
    assert names == {"helper", "public_entry"}
    assert "effectively private" in result["findings"][0]["reason"]


def test_decorated_defs_are_skipped():
    src = "from fastapi import FastAPI\n\napp = FastAPI()\n\n\n@app.get('/x')\ndef read_x():\n    return {}\n"
    assert find_unused_exports({"a.py": src})["total"] == 0


def test_dunder_and_private_and_entry_names_are_skipped():
    src = (
        "def __init__(self):\n    pass\n\n"
        "def _hidden():\n    pass\n\n"
        "def main():\n    pass\n"
    )
    assert find_unused_exports({"a.py": src})["total"] == 0


def test_class_definitions_are_flagged():
    result = find_unused_exports({"a.py": "class Widget:\n    pass\n"})
    assert result["findings"][0]["kind"] == "class"
    assert result["findings"][0]["name"] == "Widget"


def test_defs_inside_test_files_are_not_candidates():
    result = find_unused_exports({"tests/test_a.py": "def helper():\n    return 1\n"})
    assert result["total"] == 0


def test_indented_methods_are_not_candidates():
    src = "class Widget:\n    def method(self):\n        return 1\n"
    # the class itself is unused, the method must not be double-reported
    result = find_unused_exports({"a.py": src})
    assert [(f["name"], f["kind"]) for f in result["findings"]] == [("Widget", "class")]


def test_js_export_with_no_references_is_flagged():
    result = find_unused_exports({"a.ts": "export function helper() {\n  return 1;\n}\n"})
    assert result["total"] == 1
    assert result["findings"][0]["name"] == "helper"


def test_js_export_referenced_elsewhere_is_alive():
    files = {
        "a.ts": "export function helper() {\n  return 1;\n}\n",
        "b.ts": "import { helper } from './a';\nhelper();\n",
    }
    assert find_unused_exports(files)["total"] == 0


def test_findings_sorted_by_path_and_line():
    src = "def zeta():\n    pass\n\n\ndef alpha():\n    pass\n"
    result = find_unused_exports({"a.py": src})
    assert [f["name"] for f in result["findings"]] == ["zeta", "alpha"]
