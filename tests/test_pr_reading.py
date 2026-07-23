"""Tests for the PR reading mode deterministic core."""

from __future__ import annotations

from backend.services import pr_reading

SAMPLE_DIFF = """diff --git a/src/server/auth.py b/src/server/auth.py
index 1111111..2222222 100644
--- a/src/server/auth.py
+++ b/src/server/auth.py
@@ -10,6 +10,9 @@ def login(user):
     if user.locked:
         raise AuthError("locked")
+    if user.disabled:
+        raise AuthError("disabled")
+    log.info("login ok")
     return issue_token(user)
diff --git a/tests/test_auth.py b/tests/test_auth.py
index 3333333..4444444 100644
--- a/tests/test_auth.py
+++ b/tests/test_auth.py
@@ -20,3 +20,8 @@ def test_locked():
     with pytest.raises(AuthError):
         login(locked_user)
+
+
+def test_disabled():
+    with pytest.raises(AuthError):
+        login(disabled_user)
diff --git a/README.md b/README.md
index 5555555..6666666 100644
--- a/README.md
+++ b/README.md
@@ -1,3 +1,4 @@
 # sample
+Now rejects disabled users too.
"""


def test_parse_pr_url_variants():
    ref = pr_reading.parse_pr_url("https://github.com/owner/repo/pull/123")
    assert (ref.owner, ref.repo, ref.number) == ("owner", "repo", 123)
    ref = pr_reading.parse_pr_url("https://github.com/owner/repo/pull/123/files")
    assert ref.number == 123


def test_parse_pr_url_rejects_non_pr():
    for bad in ("https://github.com/owner/repo", "not a url", ""):
        try:
            pr_reading.parse_pr_url(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"accepted {bad!r}")


def test_parse_diff_files_counts_and_kinds():
    files = pr_reading.parse_diff_files(SAMPLE_DIFF)
    assert len(files) == 3
    by_path = {f.path: f for f in files}
    assert by_path["src/server/auth.py"].added == 3
    assert by_path["src/server/auth.py"].change_type == "code"
    assert by_path["tests/test_auth.py"].change_type == "test"
    assert by_path["README.md"].change_type == "docs"
    assert by_path["src/server/auth.py"].hunks


def test_reading_order_puts_biggest_code_first():
    files = pr_reading.parse_diff_files(SAMPLE_DIFF)
    ordered = pr_reading.reading_order(files)
    assert [f.change_type for f in ordered] == ["code", "test", "docs"]


def test_summarize_diff_rollup():
    files = pr_reading.parse_diff_files(SAMPLE_DIFF)
    summary = pr_reading.summarize_diff(files)
    assert summary["file_count"] == 3
    assert summary["by_kind"] == {"code": 1, "test": 1, "docs": 1}
    assert summary["biggest_file"] == "tests/test_auth.py"


def test_render_markdown_mentions_order_and_totals():
    analysis = {
        "owner": "owner",
        "repo": "repo",
        "number": 123,
        "summary": pr_reading.summarize_diff(pr_reading.parse_diff_files(SAMPLE_DIFF)),
        "files": [
            {
                "path": f.path,
                "added": f.added,
                "deleted": f.deleted,
                "change_type": f.change_type,
                "hunks": f.hunks,
            }
            for f in pr_reading.reading_order(pr_reading.parse_diff_files(SAMPLE_DIFF))
        ],
    }
    md = pr_reading.render_markdown(analysis)
    assert "owner/repo#123" in md
    assert "+9 / -0" in md
    assert "Suggested reading order" in md
