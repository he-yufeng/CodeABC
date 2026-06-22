"""Tests for backend.services.activity — project activity pulse analyser."""

from __future__ import annotations

from backend.services.activity import analyze_activity, render_activity_markdown

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_HOUR = 3600
_DAY = 86400

# Base timestamp treated as "now" in all tests (deterministic)
_NOW = 1_700_000_000  # 2023-11-14 ish


def _commit_line(ts: int, author: str = "alice", hash_: str = "abc1234") -> str:
    return f"::C::{hash_}::{ts}::{author}"


def _numstat_line(fname: str = "foo.py") -> str:
    return f"5\t2\t{fname}"


def _make_log(*entries: tuple[int, str, str]) -> str:
    """Build a git log string from (ts, author, filename) tuples."""
    lines = []
    for i, (ts, author, fname) in enumerate(entries):
        lines.append(_commit_line(ts, author, f"dead{i:04d}"))
        lines.append(_numstat_line(fname))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# No git history
# ---------------------------------------------------------------------------


class TestNoGitHistory:
    def test_none_returns_unavailable(self):
        r = analyze_activity(None)
        assert r["available"] is False

    def test_empty_string_returns_unavailable(self):
        r = analyze_activity("")
        assert r["available"] is False

    def test_unavailable_label_zh_mentions_no_history(self):
        r = analyze_activity(None)
        assert "git" in r["label_zh"] or "历史" in r["label_zh"]

    def test_unavailable_note_present(self):
        r = analyze_activity(None)
        assert len(r["notes"]) >= 1


# ---------------------------------------------------------------------------
# Empty / unparseable log
# ---------------------------------------------------------------------------


class TestEmptyLog:
    def test_empty_log_no_commits(self):
        r = analyze_activity("just some garbage text\n", now=_NOW)
        assert r["available"] is True
        assert r["total_commits"] == 0

    def test_empty_log_label_unknown(self):
        r = analyze_activity("garbage", now=_NOW)
        assert r["label"] == "unknown"


# ---------------------------------------------------------------------------
# Active project
# ---------------------------------------------------------------------------


class TestActiveProject:
    def _active_log(self) -> str:
        # 8 commits in the last 7 days
        entries = [(_NOW - i * 12 * _HOUR, "alice", f"src/a{i}.py") for i in range(8)]
        return _make_log(*entries)

    def test_label_active(self):
        r = analyze_activity(self._active_log(), now=_NOW)
        assert r["label"] == "active"

    def test_total_commits(self):
        r = analyze_activity(self._active_log(), now=_NOW)
        assert r["total_commits"] == 8

    def test_windows_week(self):
        r = analyze_activity(self._active_log(), now=_NOW)
        assert r["windows"]["week"]["commits"] == 8

    def test_windows_month_gte_week(self):
        r = analyze_activity(self._active_log(), now=_NOW)
        assert r["windows"]["month"]["commits"] >= r["windows"]["week"]["commits"]

    def test_last_commit_days_ago_small(self):
        r = analyze_activity(self._active_log(), now=_NOW)
        # newest commit is right now (offset 0)
        assert r["last_commit_days_ago"] < 1

    def test_recently_changed_files(self):
        r = analyze_activity(self._active_log(), now=_NOW)
        # should have some recently changed files
        assert len(r["recently_changed"]) >= 1


# ---------------------------------------------------------------------------
# Slowing project (1-4 commits in last 30 days)
# ---------------------------------------------------------------------------


class TestSlowingProject:
    def _slowing_log(self) -> str:
        # 3 commits in last month, last 3 months clean
        entries = [
            (_NOW - 10 * _DAY, "bob", "lib.py"),
            (_NOW - 20 * _DAY, "bob", "lib.py"),
            (_NOW - 29 * _DAY, "alice", "main.py"),
            # older commits
            (_NOW - 60 * _DAY, "alice", "old.py"),
            (_NOW - 80 * _DAY, "alice", "older.py"),
        ]
        return _make_log(*entries)

    def test_label_slowing(self):
        r = analyze_activity(self._slowing_log(), now=_NOW)
        assert r["label"] == "slowing"

    def test_label_zh_contains_slowing_keyword(self):
        r = analyze_activity(self._slowing_log(), now=_NOW)
        assert "减速" in r["label_zh"] or "slowing" in r["label_zh"].lower()


# ---------------------------------------------------------------------------
# Quiet project (0 commits in last 30d, some in last 90d)
# ---------------------------------------------------------------------------


class TestQuietProject:
    def _quiet_log(self) -> str:
        return _make_log(
            (_NOW - 45 * _DAY, "carol", "a.py"),
            (_NOW - 60 * _DAY, "carol", "b.py"),
            (_NOW - 85 * _DAY, "carol", "c.py"),
        )

    def test_label_quiet(self):
        r = analyze_activity(self._quiet_log(), now=_NOW)
        assert r["label"] == "quiet"


# ---------------------------------------------------------------------------
# Stale project (no commits in 3+ months)
# ---------------------------------------------------------------------------


class TestStaleProject:
    def _stale_log(self) -> str:
        return _make_log(
            (_NOW - 100 * _DAY, "dave", "x.py"),
            (_NOW - 150 * _DAY, "dave", "y.py"),
            (_NOW - 200 * _DAY, "dave", "z.py"),
        )

    def test_label_stale(self):
        r = analyze_activity(self._stale_log(), now=_NOW)
        assert r["label"] == "stale"


# ---------------------------------------------------------------------------
# Abandoned project (no commits in 365+ days)
# ---------------------------------------------------------------------------


class TestAbandonedProject:
    def _abandoned_log(self) -> str:
        return _make_log(
            (_NOW - 400 * _DAY, "eve", "main.py"),
            (_NOW - 500 * _DAY, "eve", "lib.py"),
        )

    def test_label_abandoned(self):
        r = analyze_activity(self._abandoned_log(), now=_NOW)
        assert r["label"] == "abandoned"

    def test_label_zh_mentions_year(self):
        r = analyze_activity(self._abandoned_log(), now=_NOW)
        assert "一年" in r["label_zh"] or "月" in r["label_zh"]


# ---------------------------------------------------------------------------
# Top contributors
# ---------------------------------------------------------------------------


class TestTopContributors:
    def test_top_contributor_most_commits(self):
        # alice has 5 commits, bob has 2
        log = _make_log(
            *[(_NOW - i * _DAY, "alice", f"a{i}.py") for i in range(5)],
            (_NOW - 6 * _DAY, "bob", "b1.py"),
            (_NOW - 7 * _DAY, "bob", "b2.py"),
        )
        r = analyze_activity(log, now=_NOW)
        top = r["top_contributors"]
        assert top[0]["author"] == "alice"
        assert top[0]["commits"] == 5
        assert any(c["author"] == "bob" for c in top)

    def test_top_contributors_capped_at_8(self):
        # 15 unique authors
        entries = [(_NOW - i * _DAY, f"user{i}", f"f{i}.py") for i in range(15)]
        log = _make_log(*entries)
        r = analyze_activity(log, now=_NOW)
        assert len(r["top_contributors"]) <= 8


# ---------------------------------------------------------------------------
# Single-author note
# ---------------------------------------------------------------------------


class TestNotes:
    def test_single_author_note(self):
        log = _make_log(
            (_NOW - 1 * _DAY, "alice", "a.py"),
            (_NOW - 2 * _DAY, "alice", "b.py"),
        )
        r = analyze_activity(log, now=_NOW)
        assert any("单人" in n or "单点" in n for n in r["notes"])

    def test_few_contributors_note(self):
        log = _make_log(
            (_NOW - 1 * _DAY, "alice", "a.py"),
            (_NOW - 2 * _DAY, "bob", "b.py"),
            (_NOW - 3 * _DAY, "carol", "c.py"),
        )
        r = analyze_activity(log, now=_NOW)
        assert any("3" in n for n in r["notes"])

    def test_many_contributors_note(self):
        entries = [(_NOW - i * _DAY, f"user{i}", f"f{i}.py") for i in range(10)]
        log = _make_log(*entries)
        r = analyze_activity(log, now=_NOW)
        assert any("10" in n for n in r["notes"])

    def test_few_commits_note(self):
        log = _make_log((_NOW - 1 * _DAY, "alice", "a.py"))
        r = analyze_activity(log, now=_NOW)
        assert any("提交数" in n or "较新" in n or "较少" in n for n in r["notes"])

    def test_notes_returned(self):
        log = _make_log((_NOW - 1 * _DAY, "alice", "a.py"))
        r = analyze_activity(log, now=_NOW)
        assert len(r["notes"]) >= 1


# ---------------------------------------------------------------------------
# Windows structure
# ---------------------------------------------------------------------------


class TestWindows:
    def test_all_windows_present(self):
        log = _make_log((_NOW - 1 * _DAY, "alice", "a.py"))
        r = analyze_activity(log, now=_NOW)
        for key in ("week", "month", "quarter", "total"):
            assert key in r["windows"]

    def test_total_window_covers_all(self):
        entries = [
            (_NOW - 5 * _DAY, "alice", "a.py"),
            (_NOW - 50 * _DAY, "alice", "b.py"),
            (_NOW - 200 * _DAY, "alice", "c.py"),
        ]
        log = _make_log(*entries)
        r = analyze_activity(log, now=_NOW)
        assert r["windows"]["total"]["commits"] == 3

    def test_week_subset_of_month(self):
        entries = [
            (_NOW - 3 * _DAY, "alice", "a.py"),
            (_NOW - 20 * _DAY, "alice", "b.py"),
        ]
        log = _make_log(*entries)
        r = analyze_activity(log, now=_NOW)
        assert r["windows"]["week"]["commits"] <= r["windows"]["month"]["commits"]

    def test_authors_deduplicated_per_window(self):
        # alice commits 3 times in week — should show up once in authors list
        entries = [(_NOW - 1 * _DAY, "alice", f"f{i}.py") for i in range(3)]
        log = _make_log(*entries)
        r = analyze_activity(log, now=_NOW)
        assert r["windows"]["week"]["authors"].count("alice") == 1

    def test_files_deduplicated_per_window(self):
        # same file touched twice in week
        entries = [
            (_NOW - 1 * _DAY, "alice", "shared.py"),
            (_NOW - 2 * _DAY, "bob", "shared.py"),
        ]
        log = _make_log(*entries)
        r = analyze_activity(log, now=_NOW)
        assert r["windows"]["week"]["files"].count("shared.py") == 1


# ---------------------------------------------------------------------------
# render_activity_markdown
# ---------------------------------------------------------------------------


class TestRenderMarkdown:
    def test_unavailable_returns_empty(self):
        r = analyze_activity(None)
        md = render_activity_markdown("MyProject", r)
        assert md == ""

    def test_none_returns_empty(self):
        assert render_activity_markdown("MyProject", None) == ""

    def test_renders_project_name(self):
        log = _make_log((_NOW - 1 * _DAY, "alice", "a.py"))
        r = analyze_activity(log, now=_NOW)
        md = render_activity_markdown("MyProject", r)
        assert "MyProject" in md

    def test_renders_label_zh(self):
        log = _make_log(*[(_NOW - i * 12 * _HOUR, "alice", f"a{i}.py") for i in range(8)])
        r = analyze_activity(log, now=_NOW)
        md = render_activity_markdown("Repo", r)
        assert r["label_zh"] in md

    def test_renders_window_table(self):
        log = _make_log((_NOW - 1 * _DAY, "alice", "a.py"))
        r = analyze_activity(log, now=_NOW)
        md = render_activity_markdown("Repo", r)
        assert "近 7 天" in md
        assert "近 30 天" in md
        assert "全部历史" in md

    def test_renders_top_contributors(self):
        log = _make_log(
            (_NOW - 1 * _DAY, "alice", "a.py"),
            (_NOW - 2 * _DAY, "bob", "b.py"),
        )
        r = analyze_activity(log, now=_NOW)
        md = render_activity_markdown("Repo", r)
        assert "alice" in md or "bob" in md

    def test_renders_recently_changed(self):
        log = _make_log((_NOW - 1 * _DAY, "alice", "src/important.py"))
        r = analyze_activity(log, now=_NOW)
        md = render_activity_markdown("Repo", r)
        assert "src/important.py" in md

    def test_ends_with_newline(self):
        log = _make_log((_NOW - 1 * _DAY, "alice", "a.py"))
        r = analyze_activity(log, now=_NOW)
        md = render_activity_markdown("Repo", r)
        assert md.endswith("\n")
