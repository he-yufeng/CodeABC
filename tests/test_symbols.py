"""Tests for backend.services.symbols — the definition index."""

from __future__ import annotations

from backend.services.symbols import (
    build_definition_index,
    file_outline,
    find_definition,
    find_references,
    public_api,
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

    def test_class_methods_are_broken_out(self):
        code = (
            "export class Store {\n"
            "  constructor(state) {\n"
            "    this.state = state;\n"
            "  }\n"
            "  async load(id) {\n"
            "    return this.fetch(id);\n"
            "  }\n"
            "  get size() {\n"
            "    return this.state.length;\n"
            "  }\n"
            "}\n"
        )
        index = build_definition_index({"store.ts": code})
        by_name = {d["name"]: d for d in index["definitions"]}
        for name in ("constructor", "load", "size"):
            assert by_name[name]["kind"] == "method"
            assert by_name[name]["parent"] == "Store"
            assert by_name[name]["qualname"] == f"Store.{name}"

    def test_typescript_return_type_method(self):
        code = "class View {\n  render(): JSX.Element {\n    return null;\n  }\n}\n"
        index = build_definition_index({"view.tsx": code})
        render = next(d for d in index["definitions"] if d["name"] == "render")
        assert render["kind"] == "method"
        assert render["parent"] == "View"

    def test_control_flow_in_method_body_is_not_a_method(self):
        # `if (...) {` and a method call inside the body read like `name(...) {`
        # / `name();` — neither should be mistaken for a class member.
        code = (
            "class Engine {\n"
            "  run(items) {\n"
            "    if (items.length) {\n"
            "      this.start();\n"
            "    }\n"
            "  }\n"
            "}\n"
        )
        index = build_definition_index({"engine.ts": code})
        names = {d["name"] for d in index["definitions"]}
        assert names == {"Engine", "run"}

    def test_outline_nests_js_methods_under_class(self):
        code = "class Box {\n  open() {}\n  close() {}\n}\n"
        result = file_outline({"box.ts": code}, "box.ts")
        box = next(n for n in result["outline"] if n["name"] == "Box")
        child_names = {c["name"] for c in box["children"]}
        assert child_names == {"open", "close"}


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

    def test_index_summary_uses_singular_for_a_lone_definition(self):
        # One class and one function: the summary should read
        # "1 class, 1 function", not the always-pluralized "1 classes,
        # 1 functions" — the same singular grammar file_outline guarantees.
        code = "class Widget:\n    pass\n\n\ndef helper():\n    pass\n"
        index = build_definition_index({"mod.py": code})
        summary = next(n for n in index["notes"] if n.startswith("Indexed"))
        assert "1 class," in summary
        assert "1 function " in summary
        assert "1 classes" not in summary
        assert "1 functions" not in summary

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


# ---------------------------------------------------------------------------
# File outline — one file's structure, in source order
# ---------------------------------------------------------------------------


class TestFileOutline:
    def test_methods_nest_under_their_class(self):
        code = """\
class Scanner:
    def __init__(self, root):
        self.root = root

    def scan(self):
        return []


def helper(x):
    return x
"""
        result = file_outline({"scanner.py": code}, "scanner.py")
        assert result["lang"] == "python"
        assert result["total"] == 4  # class + 2 methods + 1 function

        top = result["outline"]
        assert [n["name"] for n in top] == ["Scanner", "helper"]

        scanner = top[0]
        assert scanner["kind"] == "class"
        assert [c["name"] for c in scanner["children"]] == ["__init__", "scan"]
        assert all(c["kind"] == "method" for c in scanner["children"])
        assert top[1]["kind"] == "function"
        assert top[1].get("children", []) == []  # only classes carry children

    def test_source_order_is_preserved(self):
        code = "def a():\n    pass\n\n\nclass B:\n    pass\n\n\ndef c():\n    pass\n"
        result = file_outline({"m.py": code}, "m.py")
        assert [n["name"] for n in result["outline"]] == ["a", "B", "c"]
        assert [n["line"] for n in result["outline"]] == [1, 5, 9]

    def test_nested_class_nests_under_its_parent(self):
        code = """\
class Outer:
    def m(self):
        pass

    class Inner:
        def n(self):
            pass
"""
        result = file_outline({"m.py": code}, "m.py")
        outer = result["outline"][0]
        names = [c["name"] for c in outer["children"]]
        assert names == ["m", "Inner"]
        inner = next(c for c in outer["children"] if c["name"] == "Inner")
        assert [c["name"] for c in inner["children"]] == ["n"]

    def test_javascript_top_level_in_order(self):
        code = "export function load(){}\nconst save = () => {};\nclass Store {}\n"
        result = file_outline({"app.ts": code}, "app.ts")
        assert result["lang"] == "js"
        assert [n["name"] for n in result["outline"]] == ["load", "save", "Store"]

    def test_singular_counts_read_naturally(self):
        code = "class A:\n    def m(self):\n        pass\n"
        result = file_outline({"a.py": code}, "a.py")
        assert "1 class" in result["notes"][0]
        assert "1 method" in result["notes"][0]
        assert "1 classes" not in result["notes"][0]

    def test_missing_path_is_reported(self):
        result = file_outline({"a.py": "x = 1\n"}, "b.py")
        assert result["total"] == 0
        assert result["outline"] == []
        assert any("not among the analyzed files" in n for n in result["notes"])

    def test_unsupported_language_is_reported(self):
        result = file_outline({"notes.md": "# title\n"}, "notes.md")
        assert result["total"] == 0
        assert any("Python and JS/TS" in n for n in result["notes"])

    def test_empty_file_has_no_definitions(self):
        result = file_outline({"a.py": "x = 1\ny = 2\n"}, "a.py")
        assert result["total"] == 0
        assert result["outline"] == []
        assert any("No top-level functions or classes" in n for n in result["notes"])

    def test_limit_truncates_top_level_but_total_counts_all(self):
        code = "".join(f"def f{i}():\n    pass\n" for i in range(10))
        result = file_outline({"a.py": code}, "a.py", limit=3)
        assert result["total"] == 10
        assert len(result["outline"]) == 3


# ---------------------------------------------------------------------------
# Public surface — the exported flag and the public_api filter
# ---------------------------------------------------------------------------


class TestExportedFlag:
    def test_python_public_function(self):
        index = build_definition_index({"m.py": "def run():\n    pass\n"})
        run = next(d for d in index["definitions"] if d["name"] == "run")
        assert run["exported"] is True

    def test_python_underscore_function_is_internal(self):
        index = build_definition_index({"m.py": "def _helper():\n    pass\n"})
        helper = next(d for d in index["definitions"] if d["name"] == "_helper")
        assert helper["exported"] is False

    def test_python_dunder_method_is_internal(self):
        code = (
            "class Scanner:\n"
            "    def __init__(self):\n"
            "        pass\n\n"
            "    def scan(self):\n"
            "        pass\n"
        )
        index = build_definition_index({"s.py": code})
        init = next(d for d in index["definitions"] if d["name"] == "__init__")
        scan = next(d for d in index["definitions"] if d["name"] == "scan")
        assert init["exported"] is False
        assert scan["exported"] is True

    def test_python_method_of_private_class_is_internal(self):
        code = "class _Internal:\n    def run(self):\n        pass\n"
        index = build_definition_index({"m.py": code})
        cls = next(d for d in index["definitions"] if d["name"] == "_Internal")
        run = next(d for d in index["definitions"] if d["name"] == "run")
        assert cls["exported"] is False
        # a public method name does not make it public if its class is internal
        assert run["exported"] is False

    def test_js_exported_function_is_public(self):
        index = build_definition_index({"a.ts": "export function load() {}\n"})
        load = next(d for d in index["definitions"] if d["name"] == "load")
        assert load["exported"] is True

    def test_js_non_exported_function_is_internal(self):
        index = build_definition_index({"a.ts": "function helper() {}\n"})
        helper = next(d for d in index["definitions"] if d["name"] == "helper")
        assert helper["exported"] is False

    def test_js_exported_default_is_public(self):
        index = build_definition_index({"a.ts": "export default function main() {}\n"})
        main = next(d for d in index["definitions"] if d["name"] == "main")
        assert main["exported"] is True

    def test_js_exported_const_arrow_is_public(self):
        index = build_definition_index({"a.ts": "export const run = () => {}\n"})
        run = next(d for d in index["definitions"] if d["name"] == "run")
        assert run["exported"] is True

    def test_js_private_method_is_internal(self):
        code = "export class Widget {\n  render() {}\n  private tick() {}\n}\n"
        index = build_definition_index({"w.ts": code})
        render = next(d for d in index["definitions"] if d["name"] == "render")
        tick = next(d for d in index["definitions"] if d["name"] == "tick")
        assert render["exported"] is True
        assert tick["exported"] is False

    def test_js_method_of_non_exported_class_is_internal(self):
        code = "class Widget {\n  render() {}\n}\n"
        index = build_definition_index({"w.ts": code})
        render = next(d for d in index["definitions"] if d["name"] == "render")
        assert render["exported"] is False


class TestPublicApi:
    def test_keeps_only_public_names(self):
        code = "def run():\n    pass\n\n\ndef _helper():\n    pass\n"
        result = public_api({"m.py": code})
        names = [d["name"] for d in result["definitions"]]
        assert names == ["run"]
        assert result["total"] == 1

    def test_mixed_languages(self):
        py = "def parse():\n    pass\n\n\ndef _internal():\n    pass\n"
        ts = "export function load() {}\nfunction helper() {}\n"
        result = public_api({"a.py": py, "b.ts": ts})
        names = sorted(d["name"] for d in result["definitions"])
        assert names == ["load", "parse"]

    def test_sorted_alphabetically(self):
        code = "def zebra():\n    pass\n\n\ndef apple():\n    pass\n"
        result = public_api({"m.py": code})
        names = [d["name"] for d in result["definitions"]]
        assert names == ["apple", "zebra"]

    def test_notes_describe_the_convention(self):
        result = public_api({"m.py": "def run():\n    pass\n"})
        text = " ".join(result["notes"]).lower()
        assert "public" in text
        assert "underscore" in text

    def test_no_public_names_is_reported(self):
        result = public_api({"m.py": "def _a():\n    pass\n\n\ndef _b():\n    pass\n"})
        assert result["total"] == 0
        assert any("No public names" in n for n in result["notes"])

    def test_no_source_files_is_reported(self):
        result = public_api({"README.md": "# hi\n"})
        assert result["total"] == 0
        assert any("No Python or JS/TS" in n for n in result["notes"])

    def test_limit_truncates_but_total_counts_all(self):
        code = "".join(f"def f{i}():\n    pass\n\n\n" for i in range(10))
        result = public_api({"m.py": code}, limit=3)
        assert result["total"] == 10
        assert len(result["definitions"]) == 3
