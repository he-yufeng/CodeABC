"""Tests for backend.services.symbols — the definition index."""

from __future__ import annotations

from backend.services.symbols import (
    build_definition_index,
    find_definition,
    find_references,
)

# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------


class TestPython:
    def test_top_level_function(self):
        code = "def parse_config(path):\n    return {}\n"
        index = build_definition_index({"config.py": code})
        entry = next(d for d in index["definitions"] if d["name"] == "parse_config")
        assert entry["kind"] == "function"
        assert entry["parent"] is None
        assert entry["file"] == "config.py"
        assert entry["line"] == 1

    def test_async_function(self):
        code = "import asyncio\n\n\nasync def fetch(url):\n    pass\n"
        index = build_definition_index({"net.py": code})
        entry = next(d for d in index["definitions"] if d["name"] == "fetch")
        assert entry["kind"] == "function"
        assert entry["line"] == 4

    def test_class_and_methods(self):
        code = """\
class Scanner:
    def __init__(self, root):
        self.root = root

    async def scan(self):
        return []
"""
        index = build_definition_index({"scanner.py": code})
        cls = next(d for d in index["definitions"] if d["name"] == "Scanner")
        assert cls["kind"] == "class"
        assert cls["line"] == 1

        scan = next(d for d in index["definitions"] if d["name"] == "scan")
        assert scan["kind"] == "method"
        assert scan["parent"] == "Scanner"
        assert scan["qualname"] == "Scanner.scan"

    def test_nested_helper_is_skipped(self):
        code = """\
def outer():
    def inner_helper():
        return 1
    return inner_helper()
"""
        index = build_definition_index({"mod.py": code})
        names = [d["name"] for d in index["definitions"]]
        assert "outer" in names
        assert "inner_helper" not in names

    def test_method_after_dedent_is_top_level(self):
        code = """\
class A:
    def m(self):
        pass


def standalone():
    pass
"""
        index = build_definition_index({"mod.py": code})
        standalone = next(d for d in index["definitions"] if d["name"] == "standalone")
        assert standalone["kind"] == "function"
        assert standalone["parent"] is None

    def test_comment_def_ignored(self):
        code = "# def not_real():\nx = 1\n"
        index = build_definition_index({"mod.py": code})
        assert all(d["name"] != "not_real" for d in index["definitions"])


# ---------------------------------------------------------------------------
# JavaScript / TypeScript
# ---------------------------------------------------------------------------


class TestJavaScript:
    def test_function_declaration(self):
        code = "function greet(name) {\n  return name;\n}\n"
        index = build_definition_index({"app.js": code})
        entry = next(d for d in index["definitions"] if d["name"] == "greet")
        assert entry["kind"] == "function"
        assert entry["lang"] == "js"

    def test_export_function(self):
        code = "export async function loadUser(id) {\n  return id;\n}\n"
        index = build_definition_index({"user.ts": code})
        names = {d["name"]: d["kind"] for d in index["definitions"]}
        assert names.get("loadUser") == "function"

    def test_arrow_assignment(self):
        code = "const add = (a, b) => a + b;\n"
        index = build_definition_index({"math.ts": code})
        entry = next(d for d in index["definitions"] if d["name"] == "add")
        assert entry["kind"] == "function"

    def test_class_declaration(self):
        code = "export class Widget {\n  render() {}\n}\n"
        index = build_definition_index({"widget.tsx": code})
        entry = next(d for d in index["definitions"] if d["name"] == "Widget")
        assert entry["kind"] == "class"


# ---------------------------------------------------------------------------
# Index assembly + lookup
# ---------------------------------------------------------------------------


class TestIndex:
    def test_sorted_and_total(self):
        files = {
            "b.py": "def zeta():\n    pass\n",
            "a.py": "def alpha():\n    pass\n",
        }
        index = build_definition_index(files)
        names = [d["name"] for d in index["definitions"]]
        assert names == sorted(names, key=str.lower)
        assert index["total"] == 2

    def test_limit_truncates(self):
        code = "".join(f"def f{i}():\n    pass\n" for i in range(10))
        index = build_definition_index({"mod.py": code}, limit=3)
        assert index["total"] == 10
        assert len(index["definitions"]) == 3

    def test_notes_present(self):
        index = build_definition_index({"a.py": "def f():\n    pass\n"})
        assert index["notes"]
        assert any("Definitions only" in n for n in index["notes"])

    def test_empty_when_no_source(self):
        index = build_definition_index({"README.md": "# hello\n"})
        assert index["total"] == 0
        assert any("No Python or JS" in n for n in index["notes"])


class TestFindDefinition:
    def test_exact_match(self):
        files = {"scanner.py": "class Scanner:\n    pass\n"}
        hits = find_definition(files, "Scanner")
        assert len(hits) == 1
        assert hits[0]["file"] == "scanner.py"

    def test_case_insensitive_fallback(self):
        files = {"scanner.py": "class Scanner:\n    pass\n"}
        hits = find_definition(files, "scanner")
        assert len(hits) == 1
        assert hits[0]["name"] == "Scanner"

    def test_multiple_definitions_returned(self):
        files = {
            "a.py": "def handler():\n    pass\n",
            "b.py": "def handler():\n    pass\n",
        }
        hits = find_definition(files, "handler")
        assert {h["file"] for h in hits} == {"a.py", "b.py"}
        # ordered by file then line
        assert [h["file"] for h in hits] == ["a.py", "b.py"]

    def test_not_found(self):
        assert find_definition({"a.py": "x = 1\n"}, "missing") == []

    def test_blank_query(self):
        assert find_definition({"a.py": "def f():\n    pass\n"}, "  ") == []


# ---------------------------------------------------------------------------
# Find-all-references — the other half of the definition index
# ---------------------------------------------------------------------------


class TestFindReferences:
    def test_finds_definition_and_use_sites(self):
        files = {
            "config.py": "def parse_config(path):\n    return {}\n",
            "main.py": "from config import parse_config\n\ncfg = parse_config('a.toml')\n",
        }
        result = find_references(files, "parse_config")
        assert {r["file"] for r in result["references"]} == {"config.py", "main.py"}
        assert result["total"] == len(result["references"])

        defs = [r for r in result["references"] if r["is_definition"]]
        assert len(defs) == 1
        assert defs[0]["file"] == "config.py"
        assert defs[0]["line"] == 1
        # the import and the call site are uses, not definitions
        uses = [r for r in result["references"] if not r["is_definition"]]
        assert {r["file"] for r in uses} == {"main.py"}

    def test_word_boundary_rejects_partial_matches(self):
        files = {"a.py": "scan()\nscanner()\nrescan()\nmy_scan = 1\n"}
        result = find_references(files, "scan")
        assert sorted(r["line"] for r in result["references"]) == [1]

    def test_attribute_access_counts_as_use(self):
        files = {"a.py": "class S:\n    def scan(self):\n        return self.scan\n"}
        result = find_references(files, "scan")
        assert sorted(r["line"] for r in result["references"]) == [2, 3]
        by_line = {r["line"]: r["is_definition"] for r in result["references"]}
        assert by_line[2] is True  # the method definition
        assert by_line[3] is False  # self.scan is a use

    def test_comment_only_line_skipped(self):
        files = {"a.py": "# call handler here\nhandler()\n"}
        result = find_references(files, "handler")
        assert [r["line"] for r in result["references"]] == [2]

    def test_text_preview_is_trimmed(self):
        files = {"a.py": "    result = compute(x)\n"}
        result = find_references(files, "compute")
        assert result["references"][0]["text"] == "result = compute(x)"

    def test_files_count(self):
        files = {"a.py": "foo()\n", "b.py": "foo()\nfoo()\n"}
        result = find_references(files, "foo")
        assert result["files"] == 2
        assert result["total"] == 3

    def test_limit_truncates_but_total_counts(self):
        code = "".join("foo()\n" for _ in range(10))
        result = find_references({"a.py": code}, "foo", limit=3)
        assert result["total"] == 10
        assert len(result["references"]) == 3

    def test_js_reference(self):
        files = {"app.js": "function greet(n){}\ngreet('a');\n"}
        result = find_references(files, "greet")
        assert sorted(r["line"] for r in result["references"]) == [1, 2]

    def test_not_found(self):
        result = find_references({"a.py": "x = 1\n"}, "missing")
        assert result["total"] == 0
        assert result["references"] == []
        assert any("not used" in n.lower() for n in result["notes"])

    def test_blank_query(self):
        result = find_references({"a.py": "x = 1\n"}, "  ")
        assert result["total"] == 0
        assert result["references"] == []
