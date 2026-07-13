"""Tests for the config-file settings surface (pure, no repo)."""

from __future__ import annotations

from backend.services.config_files import find_config_files, render_config_files_markdown


def _by_path(result: dict) -> dict[str, dict]:
    return {f["path"]: f for f in result["files"]}


def test_no_files_is_empty():
    assert find_config_files({}) == {"total": 0, "kinds": [], "files": []}


def test_yaml_top_level_keys_only():
    yaml = "server:\n  host: 0.0.0.0\n  port: 8000\nlogging:\n  level: info\n"
    result = find_config_files({"config.yaml": yaml})
    f = _by_path(result)["config.yaml"]
    assert f["kind"] == "yaml"
    # Only the two column-0 keys are top-level; nested host/port/level are skipped.
    assert f["keys"] == ["server", "logging"]
    assert f["sections"] == []


def test_toml_sections_and_leading_keys():
    toml = (
        'name = "demo"\nversion = "1.0"\n'
        "\n[tool.ruff]\nline-length = 100\n"
        "\n[build-system]\nrequires = []\n"
    )
    result = find_config_files({"pyproject.toml": toml})
    f = _by_path(result)["pyproject.toml"]
    assert f["kind"] == "toml"
    assert f["sections"] == ["tool.ruff", "build-system"]
    # Keys above the first section header are the file's own top-level settings.
    assert f["keys"] == ["name", "version"]


def test_toml_section_first_has_no_top_level_keys():
    # A file that opens straight into a section (pyproject.toml's usual shape)
    # has no top-level settings; the first section's own keys must not leak up.
    toml = (
        '[build-system]\nrequires = ["setuptools"]\n'
        'build-backend = "setuptools.build_meta"\n'
        '\n[project]\nname = "demo"\n'
    )
    result = find_config_files({"pyproject.toml": toml})
    f = _by_path(result)["pyproject.toml"]
    assert f["sections"] == ["build-system", "project"]
    assert f["keys"] == []


def test_ini_sections():
    ini = "[flake8]\nmax-line-length = 120\n\n[isort]\nprofile = black\n"
    result = find_config_files({"tox.ini": ini})
    f = _by_path(result)["tox.ini"]
    assert f["kind"] == "ini"
    assert f["sections"] == ["flake8", "isort"]


def test_json_top_level_keys_not_nested():
    js = '{\n  "name": "demo",\n  "settings": {\n    "retries": 3\n  },\n  "debug": false\n}\n'
    result = find_config_files({"config.json": js})
    f = _by_path(result)["config.json"]
    assert f["kind"] == "json"
    # Two-space members are top-level; the deeper "retries" is skipped.
    assert f["keys"] == ["name", "settings", "debug"]


def test_data_json_without_config_name_is_ignored():
    # A config extension alone must not sweep in an ordinary data/fixture file.
    js = '{\n  "id": 1,\n  "email": "a@b.com"\n}\n'
    result = find_config_files({"fixtures/users.json": js, "data.yaml": "rows:\n"})
    assert result["files"] == []


def test_well_known_and_compound_names_recognized():
    files = {
        "setup.cfg": "[metadata]\nname = demo\n",
        "pyproject.toml": "[tool.x]\n",
        "app.config.json": '{\n  "endpoint": "http://x"\n}\n',
    }
    result = find_config_files(files)
    paths = set(_by_path(result))
    assert paths == {"setup.cfg", "pyproject.toml", "app.config.json"}


def test_richest_config_ranks_first():
    files = {
        "config.yaml": "only:\n",
        "settings.toml": "a = 1\nb = 2\n\n[x]\n\n[y]\n",
    }
    result = find_config_files(files)
    assert result["files"][0]["path"] == "settings.toml"
    assert result["kinds"] == ["toml", "yaml"]


def test_recognized_file_with_no_settings_still_surfaced():
    # An empty-ish config file is still worth telling the reader about.
    result = find_config_files({"config.yaml": "# just a comment\n"})
    f = _by_path(result)["config.yaml"]
    assert f["setting_count"] == 0
    assert result["total"] == 1


def test_render_markdown_lists_files_and_settings():
    files = {"config.yaml": "server:\nlogging:\n", "tox.ini": "[flake8]\n[isort]\n"}
    md = render_config_files_markdown("demo", find_config_files(files))
    assert "# demo — 配置文件" in md
    assert "`config.yaml`" in md
    assert "`server`" in md
    assert "`flake8`" in md


def test_render_markdown_empty_without_files():
    assert render_config_files_markdown("demo", None) == ""
    assert render_config_files_markdown("demo", {"total": 0, "files": []}) == ""
