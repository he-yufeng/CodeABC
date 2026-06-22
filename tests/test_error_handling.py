"""Tests for the silent-failures (swallowed-error) analysis."""

from __future__ import annotations

from backend.services.error_handling import (
    find_swallowed_errors,
    render_error_handling_markdown,
)


def _cats(result: dict) -> list[str]:
    return [f["category"] for f in result["findings"]]


def test_bare_except_is_flagged():
    src = "try:\n    risky()\nexcept:\n    handle()\n"
    result = find_swallowed_errors({"a.py": src})
    assert result["total"] == 1
    assert result["findings"][0]["category"] == "bare_except"
    assert result["findings"][0]["line"] == 3


def test_except_block_only_pass_is_swallowed():
    src = "try:\n    risky()\nexcept ValueError:\n    pass\n"
    result = find_swallowed_errors({"a.py": src})
    assert result["total"] == 1
    assert result["findings"][0]["category"] == "swallowed"


def test_except_ellipsis_body_is_swallowed():
    src = "try:\n    risky()\nexcept KeyError:\n    ...\n"
    result = find_swallowed_errors({"a.py": src})
    assert _cats(result) == ["swallowed"]


def test_inline_except_pass_is_swallowed():
    src = "try:\n    risky()\nexcept OSError: pass\n"
    result = find_swallowed_errors({"a.py": src})
    assert _cats(result) == ["swallowed"]


def test_except_with_real_body_is_not_flagged():
    src = "try:\n    risky()\nexcept ValueError as e:\n    logger.warning(e)\n    return None\n"
    result = find_swallowed_errors({"a.py": src})
    assert result["total"] == 0


def test_except_pass_followed_by_more_code_is_not_swallowed():
    # `pass` is not the *only* statement in the block -> not a silent swallow.
    src = "try:\n    risky()\nexcept ValueError:\n    pass\n    cleanup()\n"
    result = find_swallowed_errors({"a.py": src})
    assert result["total"] == 0


def test_comment_only_except_body_after_pass_still_swallowed():
    src = "try:\n    risky()\nexcept ValueError:\n    # known to fail sometimes\n    pass\n"
    result = find_swallowed_errors({"a.py": src})
    assert _cats(result) == ["swallowed"]


def test_word_boundary_does_not_match_identifiers():
    # `except_count` / a string containing "except" must not trip the regex.
    src = 'except_count = 0\nmsg = "except this"\nexcept_count += 1\n'
    result = find_swallowed_errors({"a.py": src})
    assert result["total"] == 0


def test_js_inline_empty_catch_is_flagged():
    src = "try {\n  risky();\n} catch (e) {}\n"
    result = find_swallowed_errors({"a.ts": src})
    assert _cats(result) == ["empty_catch"]


def test_js_empty_catch_without_binding():
    src = "try {\n  risky();\n} catch {}\n"
    result = find_swallowed_errors({"a.js": src})
    assert _cats(result) == ["empty_catch"]


def test_js_multiline_empty_catch_is_flagged():
    src = "try {\n  risky();\n} catch (e) {\n}\n"
    result = find_swallowed_errors({"a.tsx": src})
    assert _cats(result) == ["empty_catch"]


def test_js_catch_with_body_is_not_flagged():
    src = "try {\n  risky();\n} catch (e) {\n  console.error(e);\n}\n"
    result = find_swallowed_errors({"a.ts": src})
    assert result["total"] == 0


def test_js_catch_with_comment_body_is_not_flagged():
    # A comment is a *documented* decision to ignore; keep the signal high.
    src = "try {\n  risky();\n} catch (e) {\n  // intentionally ignored\n}\n"
    result = find_swallowed_errors({"a.ts": src})
    assert result["total"] == 0


def test_test_files_are_skipped():
    src = "try:\n    risky()\nexcept:\n    pass\n"
    result = find_swallowed_errors(
        {"tests/test_a.py": src, "src/a.test.ts": "try {} catch (e) {}\n"}
    )
    assert result["total"] == 0


def test_non_source_files_are_ignored():
    result = find_swallowed_errors({"README.md": "except: pass\n", "data.json": "{}"})
    assert result["total"] == 0


def test_findings_sorted_worst_first():
    src = (
        "try:\n    a()\nexcept ValueError:\n    pass\n"  # swallowed (line 3)
        "try:\n    b()\nexcept:\n    pass\n"  # bare_except (line 7)
    )
    result = find_swallowed_errors({"a.py": src})
    # bare_except (severity 0) ranks before swallowed (severity 1)
    assert _cats(result) == ["bare_except", "swallowed"]


def test_files_affected_counts_distinct_files():
    src = "try:\n    a()\nexcept:\n    pass\n"
    result = find_swallowed_errors({"a.py": src, "b.py": src})
    assert result["total"] == 2
    assert result["files_affected"] == 2


def test_limit_caps_findings_and_notes_when_truncated():
    body = "".join(f"try:\n    f{i}()\nexcept:\n    pass\n" for i in range(20))
    result = find_swallowed_errors({"a.py": body}, limit=5)
    assert result["total"] == 20
    assert len(result["findings"]) == 5
    assert any("20" in n for n in result["notes"])


def test_clean_project_has_reassuring_note():
    result = find_swallowed_errors({"a.py": "def f():\n    return 1\n"})
    assert result["total"] == 0
    assert result["notes"]


def test_render_markdown_empty_when_no_findings():
    result = find_swallowed_errors({"a.py": "x = 1\n"})
    assert render_error_handling_markdown("proj", result) == ""


def test_render_markdown_lists_findings():
    src = "try:\n    risky()\nexcept:\n    pass\n"
    result = find_swallowed_errors({"core/a.py": src})
    md = render_error_handling_markdown("proj", result)
    assert "proj — 静默失败的地方" in md
    assert "core/a.py:3" in md


def test_render_markdown_none_safe():
    assert render_error_handling_markdown("proj", None) == ""
