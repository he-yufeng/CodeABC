from backend.services.commands import find_cli_commands, render_commands_markdown


def test_click_command_with_explicit_name_and_option():
    src = (
        "import click\n"
        "\n"
        "@click.command('build')\n"
        "@click.option('--output', help='where to write')\n"
        "def build_cmd():\n"
        "    '''Build the project.'''\n"
        "    pass\n"
    )
    result = find_cli_commands({"cli.py": src})
    assert result["total"] == 1
    cmd = result["commands"][0]
    assert cmd["name"] == "build"
    assert cmd["framework"] == "click"
    assert cmd["help"] == "Build the project."
    assert "--output" in cmd["options"]
    assert cmd["path"] == "cli.py"


def test_click_command_default_name_from_function():
    src = "import click\n@click.command()\ndef deploy_app():\n    '''Deploy it.'''\n    pass\n"
    cmd = find_cli_commands({"x.py": src})["commands"][0]
    # click derives the command name from the function, turning _ into -
    assert cmd["name"] == "deploy-app"


def test_typer_command():
    src = (
        "import typer\n"
        "app = typer.Typer()\n"
        "@app.command()\n"
        "def serve():\n"
        "    '''Start the server.'''\n"
        "    pass\n"
    )
    cmd = find_cli_commands({"main.py": src})["commands"][0]
    assert cmd["name"] == "serve"
    assert cmd["framework"] == "typer"
    assert cmd["help"] == "Start the server."


def test_argparse_subparsers():
    src = (
        "import argparse\n"
        "parser = argparse.ArgumentParser()\n"
        "sub = parser.add_subparsers()\n"
        "sub.add_parser('init', help='create a new config')\n"
        "sub.add_parser('run', help='run the pipeline')\n"
    )
    result = find_cli_commands({"app.py": src})
    names = {c["name"] for c in result["commands"]}
    assert names == {"init", "run"}
    assert all(c["framework"] == "argparse" for c in result["commands"])
    helps = {c["name"]: c["help"] for c in result["commands"]}
    assert helps["init"] == "create a new config"


def test_help_falls_back_to_docstring_first_line():
    src = (
        "import click\n"
        "@click.command()\n"
        "def lint():\n"
        "    '''Check style.\n\n    More detail here.\n    '''\n"
        "    pass\n"
    )
    assert find_cli_commands({"c.py": src})["commands"][0]["help"] == "Check style."


def test_explicit_help_kwarg_beats_docstring():
    src = (
        "import click\n"
        "@click.command(help='from kwarg')\n"
        "def thing():\n"
        "    '''from docstring'''\n"
        "    pass\n"
    )
    assert find_cli_commands({"c.py": src})["commands"][0]["help"] == "from kwarg"


def test_non_python_file_skipped():
    files = {"README.md": "@click.command()\ndef x():\n    pass\n"}
    assert find_cli_commands(files)["commands"] == []


def test_syntax_error_file_is_skipped_not_crashed():
    assert find_cli_commands({"broken.py": "def (:\n  oops\n"})["commands"] == []


def test_plain_function_is_not_a_command():
    src = "import click\n\ndef helper():\n    return 1\n"
    assert find_cli_commands({"u.py": src})["commands"] == []


def test_bare_command_decorator_without_cli_import_is_ignored():
    # A `.command` decorator in a file that imports neither click nor typer is
    # almost certainly something else (a bot framework, a task queue, ...).
    src = "@bot.command()\ndef ping():\n    '''pong'''\n    pass\n"
    assert find_cli_commands({"bot.py": src})["commands"] == []


def test_frameworks_list_and_total_reported():
    src_click = "import click\n@click.command()\ndef a():\n    '''A.'''\n    pass\n"
    src_argparse = (
        "import argparse\np = argparse.ArgumentParser()\n"
        "s = p.add_subparsers()\ns.add_parser('b', help='B')\n"
    )
    result = find_cli_commands({"a.py": src_click, "b.py": src_argparse})
    assert set(result["frameworks"]) == {"click", "argparse"}
    assert result["total"] == 2


def test_render_markdown_empty_and_populated():
    assert render_commands_markdown("X", {"commands": []}) == ""
    src = "import click\n@click.command('go')\ndef go():\n    '''Go now.'''\n    pass\n"
    md = render_commands_markdown("Demo", find_cli_commands({"c.py": src}))
    assert "`go`" in md and "Go now." in md
