"""Tests for backend.services.docs — documentation coverage."""

from __future__ import annotations

from backend.services.docs import assess_doc_coverage, render_doc_coverage_markdown

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _py_code(n: int) -> str:
    """n lines of uncommented Python code."""
    return "\n".join(f"x{i} = {i}" for i in range(n))


def _py_documented(n: int) -> str:
    """A documented Python module: docstring + comments + code."""
    body = '"""Module doc."""\n'
    for i in range(n):
        body += f"# explain {i}\nx{i} = {i}\n"
    return body


# ---------------------------------------------------------------------------
# Source-file selection
# ---------------------------------------------------------------------------


class TestSelection:
    def test_empty_input(self):
        r = assess_doc_coverage({})
        assert r["total_source_files"] == 0
        assert r["under_documented"] == []

    def test_non_source_ignored(self):
        r = assess_doc_coverage({"data.json": '{"a": 1}', "README.md": "# hi"})
        assert r["total_source_files"] == 0

    def test_test_files_skipped(self):
        r = assess_doc_coverage(
            {
                "tests/test_foo.py": _py_code(40),
                "foo_test.go": "package x\n" + "var a = 1\n" * 40,
                "a.spec.ts": "const a = 1\n" * 40,
            }
        )
        assert r["total_source_files"] == 0

    def test_init_and_conftest_skipped(self):
        r = assess_doc_coverage({"pkg/__init__.py": _py_code(40), "conftest.py": _py_code(40)})
        assert r["total_source_files"] == 0

    def test_empty_content_skipped(self):
        r = assess_doc_coverage({"a.py": "", "b.py": _py_code(20)})
        assert r["total_source_files"] == 1


# ---------------------------------------------------------------------------
# Counting & flagging
# ---------------------------------------------------------------------------


class TestFlagging:
    def test_bare_large_file_flagged(self):
        r = assess_doc_coverage({"core.py": _py_code(60)})
        assert r["total_source_files"] == 1
        assert r["undocumented_files"] == 1
        assert len(r["under_documented"]) == 1
        assert r["under_documented"][0]["path"] == "core.py"
        assert r["under_documented"][0]["ratio"] == 0

    def test_small_bare_file_not_flagged(self):
        # below _MIN_CODE_LINES (15): too small to warrant a comment
        r = assess_doc_coverage({"tiny.py": _py_code(5)})
        assert r["total_source_files"] == 1
        assert r["under_documented"] == []

    def test_well_documented_not_flagged(self):
        r = assess_doc_coverage({"good.py": _py_documented(30)})
        assert r["documented_files"] == 1
        assert r["under_documented"] == []

    def test_python_docstring_counts_as_doc(self):
        content = '"""A long module docstring.\nspanning lines.\nand more.\n"""\n' + _py_code(20)
        r = assess_doc_coverage({"m.py": content})
        # docstring lines push the ratio above the under-documented threshold
        assert r["under_documented"] == []

    def test_c_style_block_comment_counts(self):
        content = "/*\n big explanation\n of the module\n across lines\n more\n */\n" + (
            "let a = 1\n" * 20
        )
        r = assess_doc_coverage({"m.ts": content})
        assert r["under_documented"] == []

    def test_line_comments_count(self):
        content = "".join(f"// note {i}\nconst x{i} = {i}\n" for i in range(30))
        r = assess_doc_coverage({"m.js": content})
        assert r["under_documented"] == []


# ---------------------------------------------------------------------------
# Ranking, percent, ordering
# ---------------------------------------------------------------------------


class TestRanking:
    def test_ranked_by_code_size_desc(self):
        r = assess_doc_coverage({"small.py": _py_code(20), "big.py": _py_code(80)})
        paths = [f["path"] for f in r["under_documented"]]
        assert paths == ["big.py", "small.py"]

    def test_doc_percent(self):
        r = assess_doc_coverage({"good.py": _py_documented(30), "bare.py": _py_code(60)})
        assert r["total_source_files"] == 2
        assert r["documented_files"] == 1
        assert r["doc_percent"] == 50

    def test_limit_caps_list(self):
        files = {f"f{i}.py": _py_code(20 + i) for i in range(20)}
        r = assess_doc_coverage(files, limit=5)
        assert len(r["under_documented"]) == 5

    def test_under_documented_has_reason(self):
        r = assess_doc_coverage({"core.py": _py_code(40)})
        assert "代码" in r["under_documented"][0]["reason"]


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------


class TestNotes:
    def test_empty_note(self):
        r = assess_doc_coverage({})
        assert any("没有" in n for n in r["notes"])

    def test_all_documented_note(self):
        r = assess_doc_coverage({"good.py": _py_documented(30)})
        assert any("文档基线不错" in n for n in r["notes"])


# ---------------------------------------------------------------------------
# render_doc_coverage_markdown
# ---------------------------------------------------------------------------


class TestRender:
    def test_none_returns_empty(self):
        assert render_doc_coverage_markdown("P", None) == ""

    def test_no_source_returns_empty(self):
        assert render_doc_coverage_markdown("P", assess_doc_coverage({})) == ""

    def test_renders_project_name_and_percent(self):
        r = assess_doc_coverage({"bare.py": _py_code(60)})
        md = render_doc_coverage_markdown("MyProj", r)
        assert "MyProj" in md
        assert "文档覆盖" in md

    def test_renders_flagged_file(self):
        r = assess_doc_coverage({"core.py": _py_code(60)})
        md = render_doc_coverage_markdown("MyProj", r)
        assert "core.py" in md
        assert "最该补文档" in md

    def test_ends_with_newline(self):
        r = assess_doc_coverage({"bare.py": _py_code(60)})
        md = render_doc_coverage_markdown("Repo", r)
        assert md.endswith("\n")
