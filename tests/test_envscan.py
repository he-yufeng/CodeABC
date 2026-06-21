"""Tests for the environment-variable surface scan (pure, no repo)."""

from __future__ import annotations

from backend.services import envscan


def _var(result, name):
    return next(v for v in result["vars"] if v["name"] == name)


def test_no_files_is_empty():
    assert envscan.scan_env_vars({}) == {"total": 0, "required": [], "vars": []}


def test_os_environ_subscript_is_required():
    result = envscan.scan_env_vars({"a.py": 'key = os.environ["API_KEY"]\n'})
    assert result["required"] == ["API_KEY"]
    var = _var(result, "API_KEY")
    assert var["required"] is True
    assert var["path"] == "a.py"
    assert var["line"] == 1


def test_getenv_and_get_with_default_are_optional():
    files = {
        "a.py": 'a = os.getenv("HOST", "localhost")\nb = os.environ.get("PORT", "8000")\n',
    }
    result = envscan.scan_env_vars(files)
    assert result["required"] == []
    assert _var(result, "HOST")["required"] is False
    assert _var(result, "PORT")["required"] is False


def test_getenv_without_default_is_optional():
    # os.getenv("X") returns None rather than raising, so it isn't required.
    result = envscan.scan_env_vars({"a.py": 'token = os.getenv("TOKEN")\n'})
    assert _var(result, "TOKEN")["required"] is False


def test_js_process_env_is_optional():
    files = {"a.js": "const a = process.env.NODE_ENV;\nconst b = process.env['PORT'];\n"}
    result = envscan.scan_env_vars(files)
    names = {v["name"] for v in result["vars"]}
    assert names == {"NODE_ENV", "PORT"}
    assert all(v["required"] is False for v in result["vars"])


def test_required_wins_when_read_both_ways():
    # Read once as os.environ["X"] (raises if unset) and once gracefully:
    # the env var is still required because the strict read will crash.
    files = {
        "a.py": 'x = os.environ["DATABASE_URL"]\n',
        "b.py": 'y = os.getenv("DATABASE_URL", "sqlite://")\n',
    }
    result = envscan.scan_env_vars(files)
    var = _var(result, "DATABASE_URL")
    assert var["required"] is True
    assert var["count"] == 2
    assert result["required"] == ["DATABASE_URL"]


def test_required_vars_rank_first():
    files = {
        "a.py": 'a = os.getenv("OPTIONAL_ONE", "x")\nb = os.environ["REQUIRED_ONE"]\n',
    }
    result = envscan.scan_env_vars(files)
    assert result["vars"][0]["name"] == "REQUIRED_ONE"


def test_render_markdown_splits_required_and_optional():
    files = {
        "svc.py": 'k = os.environ["SECRET_KEY"]\nh = os.getenv("LOG_LEVEL", "info")\n',
    }
    md = envscan.render_env_markdown("demo", envscan.scan_env_vars(files))
    assert "# demo — 环境变量" in md
    assert "## 必填（缺了会报错）：1 个" in md
    assert "## 可选（有默认值）" in md
    assert "`SECRET_KEY`" in md
    assert "`LOG_LEVEL`" in md


def test_render_markdown_empty_without_vars():
    assert envscan.render_env_markdown("demo", None) == ""
    assert envscan.render_env_markdown("demo", {"total": 0, "vars": []}) == ""
