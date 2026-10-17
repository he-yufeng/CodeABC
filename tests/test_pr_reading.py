"""Tests for the PR reading mode deterministic core."""

from __future__ import annotations

import asyncio

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


def _sample_diff() -> str:
    return (
        "diff --git a/backend/auth.py b/backend/auth.py\n"
        "--- a/backend/auth.py\n"
        "+++ b/backend/auth.py\n"
        "@@ -1,4 +1,6 @@\n"
        " import os\n"
        "+def retry_login(user):\n"
        "+    return login_with_backoff(user)\n"
        "+\n"
        " def login(user):\n"
        "     pass\n"
        "diff --git a/docs/guide.md b/docs/guide.md\n"
        "--- a/docs/guide.md\n"
        "+++ b/docs/guide.md\n"
        "@@ -1,2 +1,3 @@\n"
        " # Guide\n"
        "+New retry section.\n"
    )


def test_diff_sections_split_per_file():
    sections = pr_reading._diff_sections(_sample_diff())
    assert set(sections) == {"backend/auth.py", "docs/guide.md"}
    assert any("retry_login" in line for line in sections["backend/auth.py"])


def test_deterministic_note_names_added_symbols():
    files = pr_reading.parse_diff_files(_sample_diff())
    sections = pr_reading._diff_sections(_sample_diff())
    auth = next(f for f in files if f.path == "backend/auth.py")
    note = pr_reading._deterministic_note(auth, sections["backend/auth.py"])
    assert "retry_login" in note
    assert "production code" in note
    doc = next(f for f in files if f.path == "docs/guide.md")
    doc_note = pr_reading._deterministic_note(doc, sections["docs/guide.md"])
    assert "documentation" in doc_note


def test_explain_files_without_key_uses_deterministic_notes():
    files = pr_reading.parse_diff_files(_sample_diff())
    diff_text = _sample_diff()
    out = asyncio.run(pr_reading.explain_files(files, diff_text, api_key=None))
    assert set(out) == {"backend/auth.py", "docs/guide.md"}
    assert "retry_login" in out["backend/auth.py"]


def test_explain_files_llm_path_and_error_fallback(monkeypatch):
    files = pr_reading.parse_diff_files(_sample_diff())
    diff_text = _sample_diff()

    async def fake_ok(prompt, *, api_key=None, model=None):
        assert "docs/guide.md" in prompt or "backend/auth.py" in prompt
        return "Adds a retry helper so failed logins back off instead of giving up."

    monkeypatch.setattr("backend.services.llm.call_llm", fake_ok)
    out = asyncio.run(pr_reading.explain_files(files, diff_text, api_key="k"))
    assert out["backend/auth.py"].startswith("Adds a retry helper")

    async def fake_err(prompt, *, api_key=None, model=None):
        return "[LLM Error: boom]"

    monkeypatch.setattr("backend.services.llm.call_llm", fake_err)
    out = asyncio.run(pr_reading.explain_files(files, diff_text, api_key="k"))
    assert "retry_login" in out["backend/auth.py"]  # deterministic fallback


def test_explain_files_caps_llm_to_top_files(monkeypatch):
    # Eleven code files: only the first eight may consult the LLM; the rest get notes.
    big_diff = "".join(
        f"diff --git a/mod{i}.py b/mod{i}.py\n--- a/mod{i}.py\n+++ b/mod{i}.py\n"
        f"@@ -1,1 +1,2 @@\n+def f{i}():\n+    pass\n"
        for i in range(11)
    )
    files = pr_reading.parse_diff_files(big_diff)
    calls = []

    async def spy(prompt, *, api_key=None, model=None):
        calls.append(prompt)
        return "ok"

    monkeypatch.setattr("backend.services.llm.call_llm", spy)
    out = asyncio.run(pr_reading.explain_files(files, big_diff, api_key="k"))
    assert len(calls) == 8
    assert len(out) == 11
