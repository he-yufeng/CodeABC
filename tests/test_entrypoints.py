from backend.services.entrypoints import find_entry_points, render_entrypoints_markdown


def test_detects_main_guard_script():
    files = {"run.py": "import sys\n\n\nif __name__ == '__main__':\n    main()\n"}
    result = find_entry_points(files)
    assert result["total"] == 1
    e = result["entry_points"][0]
    assert e["kind"] == "script"
    assert e["command"] == "python run.py"


def test_no_main_guard_is_not_a_script():
    files = {"lib.py": "def helper():\n    return 1\n"}
    assert find_entry_points(files)["entry_points"] == []


def test_detects_pyproject_console_scripts():
    files = {
        "pyproject.toml": (
            "[project]\nname = 'demo'\n\n"
            '[project.scripts]\ndemo = "demo.cli:main"\ndemo-admin = "demo.admin:run"\n\n'
            "[tool.ruff]\nline-length = 100\n"
        )
    }
    result = find_entry_points(files)
    commands = {e["command"] for e in result["entry_points"]}
    assert commands == {"demo", "demo-admin"}
    assert all(e["kind"] == "command" for e in result["entry_points"])


def test_detects_package_json_bin():
    files = {"package.json": '{"name": "tool", "bin": {"tool": "./cli.js"}}'}
    result = find_entry_points(files)
    assert result["entry_points"][0]["command"] == "tool"
    assert result["entry_points"][0]["kind"] == "command"


def test_package_json_string_bin_uses_package_name():
    files = {"package.json": '{"name": "mytool", "bin": "./index.js"}'}
    assert find_entry_points(files)["entry_points"][0]["command"] == "mytool"


def test_malformed_package_json_is_ignored():
    files = {"package.json": "{ not valid json"}
    assert find_entry_points(files)["entry_points"] == []


def test_conventional_filename_is_a_fallback_entry():
    files = {"src/wsgi.py": "application = create_app()\n"}
    e = find_entry_points(files)["entry_points"][0]
    assert e["kind"] == "convention"
    assert e["path"] == "src/wsgi.py"


def test_declared_command_outranks_script_and_convention():
    files = {
        "main.py": "if __name__ == '__main__':\n    cli()\n",
        "pyproject.toml": '[project.scripts]\napp = "pkg:main"\n',
    }
    kinds = [e["kind"] for e in find_entry_points(files)["entry_points"]]
    # command first (rank 0), then the main.py script (rank 1)
    assert kinds[0] == "command"
    assert "script" in kinds


def test_render_markdown_groups_by_kind_or_empty():
    assert render_entrypoints_markdown("x", {"entry_points": []}) == ""
    files = {"pyproject.toml": '[project.scripts]\napp = "pkg:main"\n'}
    md = render_entrypoints_markdown("Demo", find_entry_points(files))
    assert "命令行命令" in md and "`app`" in md
