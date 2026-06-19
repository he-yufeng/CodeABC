"""Tests for the git-history churn analysis (pure parser, no real repo)."""

from __future__ import annotations

from collections.abc import Sequence

from backend.services import churn


def _log(*commits: tuple[str, Sequence[tuple[object, object, str]]]) -> str:
    """Build ``git log --numstat`` text from (author, [(added, deleted, path)])."""
    lines: list[str] = []
    for i, (author, files) in enumerate(commits):
        lines.append(f"{churn._COMMIT_MARKER}hash{i}::{1700000000 + i}::{author}")
        for added, deleted, path in files:
            lines.append(f"{added}\t{deleted}\t{path}")
        lines.append("")
    return "\n".join(lines)


def test_none_log_is_empty():
    result = churn.analyze_churn(None)
    assert result == {"hotspots": [], "couplings": [], "commits_analyzed": 0}


def test_hotspot_ranking_by_commit_count():
    log = _log(
        ("amy", [(10, 2, "a.py"), (1, 0, "b.py")]),
        ("amy", [(3, 1, "a.py")]),
        ("amy", [(5, 5, "a.py"), (2, 0, "b.py")]),
    )
    result = churn.analyze_churn(log)
    hotspots = result["hotspots"]
    assert result["commits_analyzed"] == 3
    # a.py changed in 3 commits, b.py in 2 -> a.py ranks first
    assert [h["path"] for h in hotspots] == ["a.py", "b.py"]
    assert hotspots[0]["commits"] == 3
    assert hotspots[0]["lines_changed"] == 10 + 2 + 3 + 1 + 5 + 5


def test_single_change_file_is_omitted():
    log = _log(("amy", [(1, 1, "once.py")]))
    result = churn.analyze_churn(log)
    assert result["hotspots"] == []  # commits < 2 threshold


def test_author_count_tracked():
    log = _log(
        ("amy", [(1, 0, "shared.py")]),
        ("bob", [(1, 0, "shared.py")]),
        ("cleo", [(1, 0, "shared.py")]),
    )
    hotspots = churn.analyze_churn(log)["hotspots"]
    assert hotspots[0]["authors"] == 3


def test_co_change_coupling_detected():
    log = _log(
        ("amy", [(1, 0, "x.py"), (1, 0, "y.py")]),
        ("amy", [(1, 0, "x.py"), (1, 0, "y.py")]),
        ("amy", [(1, 0, "x.py"), (1, 0, "y.py")]),
    )
    couplings = churn.analyze_churn(log)["couplings"]
    assert len(couplings) == 1
    c = couplings[0]
    assert {c["file_a"], c["file_b"]} == {"x.py", "y.py"}
    assert c["co_changes"] == 3
    assert c["coupling"] == 100  # both files always changed together


def test_coupling_support_filter():
    log = _log(
        ("amy", [(1, 0, "x.py"), (1, 0, "y.py")]),
        ("amy", [(1, 0, "x.py"), (1, 0, "y.py")]),
    )
    # co-change only twice, below default min_coupling_support=3
    assert churn.analyze_churn(log)["couplings"] == []
    # ...but surfaces when the threshold is lowered
    assert len(churn.analyze_churn(log, min_coupling_support=2)["couplings"]) == 1


def test_scanned_paths_filter():
    log = _log(
        ("amy", [(1, 0, "src/keep.py"), (1, 0, "node_modules/skip.js")]),
        ("amy", [(1, 0, "src/keep.py"), (1, 0, "node_modules/skip.js")]),
    )
    result = churn.analyze_churn(log, scanned_paths={"src/keep.py"}, min_coupling_support=2)
    paths = {h["path"] for h in result["hotspots"]}
    assert paths == {"src/keep.py"}
    # the dropped file can't form a coupling pair either
    assert result["couplings"] == []


def test_rename_normalization():
    log = _log(
        ("amy", [(1, 0, "pkg/{old => new}/mod.py")]),
        ("amy", [(1, 0, "pkg/new/mod.py")]),
    )
    # brace-form rename folds onto the post-rename path
    log2 = _log(
        ("amy", [(1, 0, "a.py => b.py")]),
        ("amy", [(1, 0, "b.py")]),
    )
    h1 = churn.analyze_churn(log)["hotspots"]
    assert h1 and h1[0]["path"] == "pkg/new/mod.py"
    assert h1[0]["commits"] == 2
    h2 = churn.analyze_churn(log2)["hotspots"]
    assert h2 and h2[0]["path"] == "b.py"
    assert h2[0]["commits"] == 2


def test_binary_files_counted_without_line_churn():
    log = _log(
        ("amy", [("-", "-", "logo.png")]),
        ("amy", [("-", "-", "logo.png")]),
    )
    hotspots = churn.analyze_churn(log)["hotspots"]
    assert hotspots[0]["path"] == "logo.png"
    assert hotspots[0]["commits"] == 2
    assert hotspots[0]["lines_changed"] == 0  # "-" binary markers don't add churn


def test_render_markdown_empty_when_no_history():
    assert churn.render_churn_markdown("proj", None) == ""
    assert churn.render_churn_markdown("proj", {"hotspots": [], "couplings": []}) == ""


def test_render_markdown_contains_sections():
    log = _log(
        ("amy", [(5, 2, "core.py"), (1, 0, "util.py")]),
        ("bob", [(3, 1, "core.py"), (1, 0, "util.py")]),
        ("amy", [(2, 0, "core.py"), (1, 0, "util.py")]),
    )
    data = churn.analyze_churn(log, min_coupling_support=2)
    md = churn.render_churn_markdown("demo", data)
    assert "# demo — 变更历史" in md
    assert "## 变更热点" in md
    assert "## 变更耦合" in md
    assert "`core.py`" in md
    assert "`core.py` ↔ `util.py`" in md or "`util.py` ↔ `core.py`" in md
    assert md.endswith("\n")


def test_bulk_commit_skips_coupling_but_counts_changes():
    many = [(1, 0, f"f{i}.py") for i in range(churn._MAX_FILES_FOR_COUPLING + 5)]
    log = _log(
        ("amy", many),
        ("amy", many),
        ("amy", many),
    )
    result = churn.analyze_churn(log, limit=100)
    # every file still registers as a hotspot (changed 3x)...
    assert len(result["hotspots"]) == churn._MAX_FILES_FOR_COUPLING + 5
    assert all(h["commits"] == 3 for h in result["hotspots"])
    # ...but the oversized commits generate no coupling noise
    assert result["couplings"] == []
