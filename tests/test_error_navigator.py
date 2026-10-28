from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app import app
from backend.routers.project import _projects
from backend.services.error_navigator import locate_error

FILES = {
    "backend/app.py": "import os\n\n\ndef run():\n    return 1 / 0\n",
    "frontend/src/index.ts": "export const run = () => {\n  throw new Error('boom')\n}\n",
    "cmd/server/main.go": 'package main\n\nfunc main() {\n\tpanic("boom")\n}\n',
}


def test_python_traceback_uses_project_suffix_and_source_excerpt():
    log = 'Traceback:\n  File "/work/demo/backend/app.py", line 5, in run\nValueError: boom'

    result = locate_error(log, FILES)

    assert result["unresolved"] == 0
    assert result["locations"] == [
        {
            "path": "backend/app.py",
            "line": 5,
            "column": None,
            "kind": "Python 源码",
            "purpose": "一段 Python 程序代码。",
            "excerpt": "   3 | \n   4 | def run():\n   5 |     return 1 / 0",
        }
    ]


def test_node_and_go_frames_support_file_urls_windows_and_columns():
    log = """
Error: boom
    at run (file:///work/demo/frontend/src/index.ts:2:9)
    at C:\\work\\demo\\cmd\\server\\main.go:4:2
"""

    result = locate_error(log, FILES)

    assert [(item["path"], item["line"], item["column"]) for item in result["locations"]] == [
        ("frontend/src/index.ts", 2, 9),
        ("cmd/server/main.go", 4, 2),
    ]


def test_duplicate_frames_and_out_of_range_lines_do_not_create_false_locations():
    log = """
  File "/work/demo/backend/app.py", line 5, in run
  File "/work/demo/backend/app.py", line 5, in run
  File "/work/demo/backend/app.py", line 500, in run
  File "/tmp/site-packages/other.py", line 9, in dependency
"""

    result = locate_error(log, FILES)

    assert len(result["locations"]) == 1
    assert result["unresolved"] == 2


def test_ambiguous_basename_is_not_guessed_but_longest_suffix_wins():
    files = {
        "src/app.py": "x = 1\n",
        "tests/app.py": "x = 2\n",
        "backend/src/app.py": "x = 3\n",
    }

    ambiguous = locate_error('  File "app.py", line 1, in run', files)
    longest = locate_error('  File "/repo/backend/src/app.py", line 1, in run', files)

    assert ambiguous["locations"] == []
    assert ambiguous["unresolved"] == 1
    assert longest["locations"][0]["path"] == "backend/src/app.py"


def test_empty_or_unrelated_log_returns_an_honest_empty_result():
    assert locate_error("nothing useful here", FILES) == {
        "locations": [],
        "unresolved": 0,
        "truncated": False,
    }


def test_output_is_capped_without_losing_the_first_frames():
    files = {"app.py": "\n".join(f"line {number}" for number in range(1, 30))}
    log = "\n".join(f'  File "/repo/app.py", line {number}, in run' for number in range(1, 26))

    result = locate_error(log, files)

    assert len(result["locations"]) == 20
    assert result["locations"][0]["line"] == 1
    assert result["locations"][-1]["line"] == 20
    assert result["truncated"] is True


def test_http_endpoint_returns_locations_and_preserves_project_scope():
    project_id = "trace-demo"
    _projects[project_id] = {"name": "demo", "files": [], "file_contents": FILES}
    client = TestClient(app)
    try:
        response = client.post(
            f"/api/project/{project_id}/error-locations",
            json={"log": '  File "/elsewhere/backend/app.py", line 5, in run'},
        )
        missing = client.post(
            "/api/project/not-a-project/error-locations",
            json={"log": '  File "app.py", line 1, in run'},
        )
    finally:
        _projects.pop(project_id, None)

    assert response.status_code == 200
    assert response.json()["locations"][0]["path"] == "backend/app.py"
    assert response.json()["locations"][0]["line"] == 5
    assert missing.status_code == 404


def test_http_endpoint_rejects_oversized_logs():
    client = TestClient(app)
    response = client.post(
        "/api/project/trace-demo/error-locations",
        json={"log": "x" * 200_001},
    )

    assert response.status_code == 422
