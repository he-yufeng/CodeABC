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


def test_environ_setdefault_is_optional():
    # os.environ.setdefault("X", ...) always supplies a fallback, so X is optional.
    result = envscan.scan_env_vars({"a.py": 'os.environ.setdefault("FEATURE_FLAG", "off")\n'})
    assert _var(result, "FEATURE_FLAG")["required"] is False


def test_js_process_env_is_optional():
    files = {"a.js": "const a = process.env.NODE_ENV;\nconst b = process.env['PORT'];\n"}
    result = envscan.scan_env_vars(files)
    names = {v["name"] for v in result["vars"]}
    assert names == {"NODE_ENV", "PORT"}
    assert all(v["required"] is False for v in result["vars"])


def test_decouple_config_required_and_optional():
    # python-decouple: a bare config("X") raises when unset (required); a default
    # arg (trailing comma) makes it optional.
    files = {"a.py": 'k = config("SECRET_KEY")\np = config("PORT", default=8000)\n'}
    result = envscan.scan_env_vars(files)
    assert _var(result, "SECRET_KEY")["required"] is True
    assert _var(result, "PORT")["required"] is False
    assert result["required"] == ["SECRET_KEY"]


def test_environs_env_readers_required_and_optional():
    # environs / django-environ: a bare env("X") / env.int("X") is required; a
    # default arg makes it optional.
    files = {
        "settings.py": (
            'db = env("DATABASE_URL")\n'
            'port = env.int("PORT", 8000)\n'
            'debug = env.bool("DEBUG", default=False)\n'
        ),
    }
    result = envscan.scan_env_vars(files)
    assert _var(result, "DATABASE_URL")["required"] is True
    assert _var(result, "PORT")["required"] is False
    assert _var(result, "DEBUG")["required"] is False
    assert result["required"] == ["DATABASE_URL"]


def test_go_getenv_and_lookupenv_are_optional():
    files = {
        "main.go": 'port := os.Getenv("PORT")\n_, ok := os.LookupEnv("HOME_DIR")\n',
    }
    result = envscan.scan_env_vars(files)
    names = {v["name"]: v["required"] for v in result["vars"]}
    assert names == {"PORT": False, "HOME_DIR": False}


def test_rust_env_var_required_on_unwrap_optional_otherwise():
    files = {
        "main.rs": (
            'let url = env::var("DATABASE_URL").unwrap();\n'
            'let key = std::env::var("API_KEY").expect("missing key");\n'
            'let lvl = env::var("LOG_LEVEL").unwrap_or("info".into());\n'
            'let raw = env::var("RAW_HANDLED");\n'
        ),
    }
    result = envscan.scan_env_vars(files)
    names = {v["name"]: v["required"] for v in result["vars"]}
    assert names == {
        "DATABASE_URL": True,
        "API_KEY": True,
        "LOG_LEVEL": False,
        "RAW_HANDLED": False,
    }


def test_env_loader_patterns_do_not_match_stdlib_or_attribute_calls():
    # os.getenv / os.environ.get must not also match the environs env(...) rule
    # (their "env" is preceded by a word char / dot), and attribute calls like
    # app.config(...) / self.env(...) must not match the decouple/environs rules.
    files = {
        "a.py": (
            'a = os.getenv("TOKEN")\n'
            'b = os.environ.get("HOST", "x")\n'
            'c = app.config("DEBUG")\n'
            'd = self.env("NOISE")\n'
        ),
    }
    result = envscan.scan_env_vars(files)
    names = {v["name"] for v in result["vars"]}
    assert names == {"TOKEN", "HOST"}
    assert _var(result, "TOKEN")["count"] == 1  # not double-counted by the env rule


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


def test_undocumented_env_vars_flags_only_missing_names():
    files = {
        "app.py": 'a = os.environ["SECRET_TOKEN"]\nb = os.getenv("FEATURE_FLAG", "on")\n',
        "README.md": "Set `SECRET_TOKEN` before running.",
    }
    scan = envscan.scan_env_vars(files)
    assert envscan.find_undocumented_env_vars(scan, files) == ["FEATURE_FLAG"]


def test_undocumented_env_vars_counts_env_example_as_docs():
    files = {
        "app.py": 'a = os.environ["DB_HOST"]\nb = os.environ["DB_PORT"]\n',
        ".env.example": "DB_HOST=localhost\n",
    }
    scan = envscan.scan_env_vars(files)
    assert envscan.find_undocumented_env_vars(scan, files) == ["DB_PORT"]


def test_undocumented_env_vars_whole_word_matching():
    files = {
        "app.py": 'a = os.environ["HOST"]\n',
        "README.md": "DB_HOST=something",
    }
    scan = envscan.scan_env_vars(files)
    assert envscan.find_undocumented_env_vars(scan, files) == ["HOST"]


def test_undocumented_env_vars_ignores_source_only_mentions():
    files = {
        "app.py": 'a = os.environ["INTERNAL_KEY"]\n',
        "other.py": "# INTERNAL_KEY is loaded here\n",
    }
    scan = envscan.scan_env_vars(files)
    assert envscan.find_undocumented_env_vars(scan, files) == ["INTERNAL_KEY"]
