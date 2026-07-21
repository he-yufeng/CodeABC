"""Tests for the duplicate-code analyzer."""

from backend.services.duplicate_code import render_duplicate_code_markdown, scan_duplicate_code

_BLOCK = "\n".join(f"value_{i} = compute({i})" for i in range(7))


def _files(**kwargs):
    return kwargs


def test_no_duplicates_returns_empty():
    result = scan_duplicate_code(_files(a="x = 1\n" * 6 + "\ny = 2\n" * 6))
    assert result["clusters"] == []
    assert result["total"] == 0
    assert render_duplicate_code_markdown("demo", result) == ""


def test_cross_file_duplication_is_flagged_with_real_lines():
    files = _files(
        **{
            "a.py": f"start = 0\n{_BLOCK}\nend = 1",
            "b.py": f"other = 2\n\n# a comment\n{_BLOCK}\n",
        }
    )
    result = scan_duplicate_code(files)
    assert result["total"] == 1
    cluster = result["clusters"][0]
    # one occurrence per physical copy, at its real line: a.py line 2,
    # b.py line 4 (blank/comment lines count toward the reported line number
    # even though they are not hashed)
    assert cluster == [{"path": "a.py", "line": 2}, {"path": "b.py", "line": 4}]


def test_same_file_needs_three_copies():
    two = f"{_BLOCK}\nx = 0\n{_BLOCK}"
    assert scan_duplicate_code(_files(**{"a.py": two}))["total"] == 0
    three = f"{_BLOCK}\nx = 0\n{_BLOCK}\ny = 1\n{_BLOCK}"
    result = scan_duplicate_code(_files(**{"a.py": three}))
    assert result["total"] == 1
    assert len(result["clusters"][0]) == 3


def test_imports_and_comments_do_not_match():
    files = _files(
        **{
            "a.py": "import os\nfrom x import y\n# shared comment\n" + _BLOCK,
            "b.py": "import os\nfrom x import y\n# shared comment\n",
        }
    )
    assert scan_duplicate_code(files)["total"] == 0


def test_test_files_are_skipped():
    files = _files(
        **{
            "a.py": _BLOCK,
            "test_a.py": _BLOCK,
            "tests/test_b.py": _BLOCK,
        }
    )
    assert scan_duplicate_code(files)["total"] == 0


def test_window_is_configurable():
    short = "a = 1\nb = 2\nc = 3\nd = 4"
    files = _files(**{"a.py": short, "b.py": short})
    assert scan_duplicate_code(files, window=4)["total"] == 1
    assert scan_duplicate_code(files, window=6)["total"] == 0


def test_render_lists_all_spots():
    files = _files(**{"a.py": _BLOCK, "pkg/b.py": _BLOCK})
    md = render_duplicate_code_markdown("demo", scan_duplicate_code(files))
    assert "## 重复的代码（demo）" in md
    assert "`a.py`" in md and "`pkg/b.py`" in md
