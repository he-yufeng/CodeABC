"""Tests for the tech-debt marker scan (pure, no repo)."""

from __future__ import annotations

from backend.services import techdebt


def test_no_files_is_empty():
    result = techdebt.scan_tech_debt({})
    assert result == {"total": 0, "by_kind": {}, "files": []}


def test_collects_markers_with_kind_line_and_note():
    files = {
        "a.py": "x = 1\n# TODO: wire up retries\ny = 2\n# FIXME broken on windows\n",
    }
    result = techdebt.scan_tech_debt(files)
    assert result["total"] == 2
    assert result["by_kind"] == {"TODO": 1, "FIXME": 1}
    markers = result["files"][0]["markers"]
    assert markers[0] == {"line": 2, "kind": "TODO", "note": "wire up retries"}
    # punctuation after the marker is stripped from the note
    assert markers[1] == {"line": 4, "kind": "FIXME", "note": "broken on windows"}


def test_lowercase_prose_is_not_a_marker():
    # whole-word upper-case only: prose must not be mistaken for a marker
    files = {"doc.py": "# this is my todo list and some debugging notes\n"}
    assert techdebt.scan_tech_debt(files)["total"] == 0


def test_marker_must_be_whole_word():
    # HACK should match, but a word merely containing it must not
    files = {"m.py": "# HACK around the cache\nvalue = hackathon_score\n"}
    result = techdebt.scan_tech_debt(files)
    assert result["by_kind"] == {"HACK": 1}


def test_files_ranked_by_marker_count():
    files = {
        "few.py": "# TODO one\n",
        "many.py": "# TODO a\n# FIXME b\n# XXX c\n",
    }
    ranked = techdebt.scan_tech_debt(files)["files"]
    assert [f["path"] for f in ranked] == ["many.py", "few.py"]
    assert ranked[0]["count"] == 3


def test_per_file_and_overall_limits():
    body = "".join(f"# TODO item {i}\n" for i in range(10))
    files = {f"f{i}.py": body for i in range(20)}
    result = techdebt.scan_tech_debt(files, limit=3, per_file_limit=2)
    assert result["total"] == 200  # all markers are still counted
    assert len(result["files"]) == 3  # but only the top 3 files are returned
    assert len(result["files"][0]["markers"]) == 2  # capped per file


def test_render_markdown_groups_by_kind_and_file():
    files = {"svc.py": "# TODO: add caching\n# HACK: skip validation for now\n"}
    data = techdebt.scan_tech_debt(files)
    md = techdebt.render_techdebt_markdown("demo", data)
    assert "# demo — 待办与技术债" in md
    assert "## 按类型" in md
    assert "## 标记最多的文件" in md
    assert "`svc.py` — 2 处" in md
    assert "L1 `TODO`：add caching" in md


def test_render_markdown_empty_without_markers():
    assert techdebt.render_techdebt_markdown("demo", None) == ""
    assert techdebt.render_techdebt_markdown("demo", {"total": 0, "files": []}) == ""
