"""Tests for the git-history ownership analysis (pure parser, no real repo)."""

from __future__ import annotations

from collections.abc import Sequence

from backend.services import churn, ownership


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
    assert ownership.analyze_ownership(None) == {
        "owners": [],
        "silos": [],
        "commits_analyzed": 0,
    }


def test_single_commit_file_is_omitted():
    log = _log(("amy", [(1, 1, "once.py")]))
    assert ownership.analyze_ownership(log)["owners"] == []


def test_solo_author_is_full_ownership_and_silo():
    log = _log(
        ("amy", [(1, 0, "solo.py")]),
        ("amy", [(2, 1, "solo.py")]),
        ("amy", [(3, 0, "solo.py")]),
    )
    result = ownership.analyze_ownership(log)
    owner = result["owners"][0]
    assert owner["path"] == "solo.py"
    assert owner["primary_author"] == "amy"
    assert owner["ownership"] == 100
    assert owner["authors"] == 1
    assert owner["bus_factor"] == 1
    # 3 commits, one person, 100% -> flagged as a knowledge silo
    assert [s["path"] for s in result["silos"]] == ["solo.py"]


def test_evenly_shared_file_has_bus_factor_two_and_is_not_a_silo():
    log = _log(
        ("amy", [(1, 0, "shared.py")]),
        ("bob", [(1, 0, "shared.py")]),
        ("amy", [(1, 0, "shared.py")]),
        ("bob", [(1, 0, "shared.py")]),
    )
    owner = ownership.analyze_ownership(log)["owners"][0]
    assert owner["authors"] == 2
    assert owner["ownership"] == 50
    # 50/50 split: a single author is not a majority, so the bus factor is 2
    assert owner["bus_factor"] == 2
    assert ownership.analyze_ownership(log)["silos"] == []


def test_dominant_owner_is_silo_even_with_a_second_author():
    log = _log(
        ("amy", [(1, 0, "lead.py")]),
        ("amy", [(1, 0, "lead.py")]),
        ("amy", [(1, 0, "lead.py")]),
        ("amy", [(1, 0, "lead.py")]),
        ("bob", [(1, 0, "lead.py")]),
    )
    result = ownership.analyze_ownership(log)
    owner = result["owners"][0]
    assert owner["ownership"] == 80  # amy 4 of 5 commits
    assert owner["bus_factor"] == 1  # amy alone is a majority
    assert [s["path"] for s in result["silos"]] == ["lead.py"]


def test_scanned_paths_filters_out_unscanned_files():
    log = _log(
        ("amy", [(1, 0, "keep.py"), (1, 0, "drop.py")]),
        ("amy", [(1, 0, "keep.py"), (1, 0, "drop.py")]),
    )
    result = ownership.analyze_ownership(log, scanned_paths={"keep.py"})
    assert [o["path"] for o in result["owners"]] == ["keep.py"]


def test_owners_ranked_by_commit_count():
    log = _log(
        ("amy", [(1, 0, "busy.py"), (1, 0, "quiet.py")]),
        ("bob", [(1, 0, "busy.py")]),
        ("amy", [(1, 0, "busy.py"), (1, 0, "quiet.py")]),
    )
    owners = ownership.analyze_ownership(log)["owners"]
    # busy.py: 3 commits, quiet.py: 2 -> busy ranks first
    assert [o["path"] for o in owners] == ["busy.py", "quiet.py"]
    assert owners[0]["commits"] == 3


def test_render_markdown_has_owner_and_silo_sections():
    log = _log(
        ("amy", [(1, 0, "solo.py")]),
        ("amy", [(2, 1, "solo.py")]),
        ("amy", [(3, 0, "solo.py")]),
    )
    data = ownership.analyze_ownership(log)
    md = ownership.render_ownership_markdown("demo", data)
    assert "# demo — 代码归属" in md
    assert "## 谁在维护（按改动次数）" in md
    assert "## 知识孤岛（只压在一个人身上）" in md
    assert "solo.py" in md
    assert "amy" in md


def test_render_markdown_empty_without_history():
    assert ownership.render_ownership_markdown("demo", None) == ""
    assert ownership.render_ownership_markdown("demo", {"owners": [], "silos": []}) == ""
