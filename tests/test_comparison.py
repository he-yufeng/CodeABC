"""Source snippets are inert scanner inputs; none of the uploaded code is executed."""

import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.services import comparison


def files(**contents):
    return [{"path": path, "content": content} for path, content in contents.items()]


def compare(before, after):
    return comparison.compare_projects(files(**before), files(**after))


def test_changes_use_content_not_size_and_leave_inputs_untouched():
    before = {"same.py": "x = 1\n", "edited.py": "a = 1\n", "deleted.py": "pass\n"}
    after = {"same.py": "x = 1\n", "edited.py": "a = 2\n", "new.py": "pass\n"}
    original = before.copy(), after.copy()
    report = compare(before, after)
    assert report["summary"] == {
        "added": 1,
        "deleted": 1,
        "modified": 1,
        "unchanged": 1,
        "not_compared": 0,
    }
    edited = next(f for f in report["files"] if f["path"] == "edited.py")
    assert edited["before_bytes"] == edited["after_bytes"]
    assert edited["before_hash"] != edited["after_hash"]
    assert "-a = 1" in edited["diff"] and "+a = 2" in edited["diff"]
    assert (before, after) == original


def test_empty_snapshots_and_empty_files_are_distinct_from_missing_files():
    assert compare({}, {})["summary"]["unchanged"] == 0
    added = compare({}, {"empty.py": ""})
    assert added["summary"]["added"] == 1
    assert added["files"][0]["before_hash"] is None
    assert added["files"][0]["after_hash"] is not None
    assert compare({"empty.py": ""}, {})["summary"]["deleted"] == 1
    assert compare({"empty.py": ""}, {"empty.py": ""})["summary"]["unchanged"] == 1


def test_no_changes_report_is_stable_and_never_runs_uploaded_code():
    source = "raise AssertionError('this is only source text')\n"
    report = compare({"app.py": source}, {"app.py": source})
    assert report["files"] == []
    assert report["summary"]["unchanged"] == 1
    assert report["security"]["introduced"] == 0


def test_utf8_sizes_and_newline_only_edits_remain_visible():
    report = compare({"app.py": "你好\r\n"}, {"app.py": "你好\n"})
    assert report["summary"]["modified"] == 1
    assert report["files"][0]["before_bytes"] == 8
    assert report["files"][0]["after_bytes"] == 7


def test_paths_match_across_windows_separators():
    report = comparison.compare_projects(
        [{"path": "src\\app.py", "content": "x=1"}],
        [{"path": "src/app.py", "content": "x=1"}],
    )
    assert report["summary"]["unchanged"] == 1


def test_duplicate_normalized_paths_are_rejected():
    with pytest.raises(ValueError, match="Duplicate file path"):
        comparison.compare_projects(
            [{"path": "app.py", "content": "x=1"}, {"path": "./app.py", "content": "x=2"}], []
        )


def test_sensitive_generated_unsafe_and_binary_files_stay_out_of_reports():
    source = {
        "app.py": "x=1",
        ".env": "DO_NOT_INCLUDE_THIS_VALUE",
        "node_modules/pkg/index.js": "eval('not source')",
        "../escape.py": "eval('not source')",
        "binary.py": "\0eval('not source')",
        "bundle.min.js": "eval('not source')",
    }
    report = compare({}, source)
    assert [f["path"] for f in report["files"]] == ["app.py"]
    assert report["summary"]["not_compared"] == 5
    assert report["security"]["after_total"] == 0
    assert "DO_NOT_INCLUDE_THIS_VALUE" not in str(report)


def test_filtered_new_file_is_unknown_not_a_deletion_or_a_resolved_warning():
    report = compare({"app.py": "eval(value)\n"}, {"app.py": "x" * (100 * 1024 + 1)})
    assert report["files"] == []
    assert report["summary"]["deleted"] == 0
    assert report["excluded_paths"] == ["app.py"]
    assert report["security"]["no_longer_detected"] == 0


def test_finding_deltas_keep_old_and_new_locations_without_line_shift_noise():
    report = compare(
        {"app.py": "eval(value)\nDEBUG = True\n"},
        {"app.py": "# heading\neval(value)\nos.system(command)\n"},
    )
    delta = report["security"]
    assert delta["complete"]
    assert (delta["introduced"], delta["no_longer_detected"], delta["persistent"]) == (1, 1, 1)
    matched = next(f for f in delta["changes"] if f["status"] == "persistent")
    assert matched["before"]["line"] == 1
    assert matched["after"]["line"] == 2
    assert (
        next(f for f in delta["changes"] if f["status"] == "introduced")["after"]["category"]
        == "shell_injection"
    )


def test_duplicate_warning_lines_are_matched_as_a_multiset():
    delta = compare({"app.py": "eval(value)\neval(value)\n"}, {"app.py": "eval(value)\n"})[
        "security"
    ]
    assert delta["persistent"] == 1
    assert delta["no_longer_detected"] == 1
    assert delta["introduced"] == 0


def test_truncated_scans_do_not_claim_findings_disappeared(monkeypatch):
    monkeypatch.setattr(comparison, "_MAX_FINDINGS", 1)
    delta = compare({"app.py": "eval(a)\neval(b)\n"}, {})["security"]
    assert not delta["complete"]
    assert delta["before_total"] == 2
    assert delta["no_longer_detected"] is None
    assert delta["changes"] == []


def test_diff_preview_is_bounded_without_hiding_the_file_change():
    report = compare({"big.py": "x=1\n" * 2100}, {"big.py": "x=2\n" * 2100})
    assert report["summary"]["modified"] == 1
    assert report["files"][0]["diff_truncated"]
    report = compare({"a.txt": "a" * 9000}, {"a.txt": "b" * 9000})
    assert len(report["files"][0]["diff"]) <= 8000
    assert report["files"][0]["diff_truncated"]


def test_snapshot_budget_counts_bytes_not_characters(monkeypatch):
    monkeypatch.setattr(comparison, "_MAX_SNAPSHOT_BYTES", 8)
    with pytest.raises(ValueError, match="at most 5 MiB"):
        compare({}, {"a.txt": "你好啊"})


def test_http_comparison_is_available_without_a_key_and_does_not_save_projects(monkeypatch):
    from backend.services import cache

    async def must_not_save(*args, **kwargs):
        raise AssertionError("Comparisons must not persist uploaded code")

    monkeypatch.setattr(cache, "save_project", must_not_save)
    response = TestClient(app).post(
        "/api/project/compare",
        json={
            "before": {"project_name": "old", "files": files(**{"app.py": "x=1"})},
            "after": {"project_name": "new", "files": files(**{"app.py": "x=2"})},
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["schema_version"] == 1
    assert result["before_name"] == "old" and result["after_name"] == "new"
    assert result["summary"]["modified"] == 1


def test_http_limits_reject_instead_of_silently_truncating_files():
    response = TestClient(app).post(
        "/api/project/compare",
        json={
            "before": {"files": files(**{f"{i}.py": "pass" for i in range(501)})},
            "after": {"files": []},
        },
    )
    assert response.status_code == 422


def test_http_ambiguous_paths_return_a_clear_error():
    response = TestClient(app).post(
        "/api/project/compare",
        json={
            "before": {"files": [{"path": "a.py", "content": ""}] * 2},
            "after": {"files": []},
        },
    )
    assert response.status_code == 400
    assert "Duplicate file path" in response.json()["detail"]
