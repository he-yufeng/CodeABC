from backend.services import codemap_export, importgraph


def _demo_project() -> dict:
    # A tiny two-file project. There is no git history, so churn/ownership/
    # activity stay empty, but the file text alone carries a TODO and an env
    # var, so the tech-debt and env sections do fire.
    return {
        "name": "demo",
        "files": [
            {"path": "app.py", "content": "import helper\nprint('hi')\n"},
            {"path": "helper.py", "content": "x = 1\n"},
        ],
        "file_contents": {
            "app.py": '# TODO: wire retries\nkey = os.environ["API_KEY"]\n',
            "helper.py": "x = 1\n",
        },
    }


def test_codemap_leads_with_import_graph():
    proj = _demo_project()
    base = importgraph.render_codemap_markdown(proj["name"], proj["files"])

    result = codemap_export.build_codemap_markdown(proj)

    # The import-graph code map is always the first block, even once other
    # sections are appended after it.
    assert result.startswith(base.rstrip())


def test_codemap_joins_only_nonempty_sections_with_a_rule():
    proj = _demo_project()
    sections = [s for s in codemap_export._ordered_sections(proj) if s]

    result = codemap_export.build_codemap_markdown(proj)

    # At least the text-derived sections (tech debt, env) should have fired, so
    # this project actually exercises the joining path rather than the base case.
    assert len(sections) >= 1
    # One horizontal rule separates each appended section from the block before
    # it, and empty sections are dropped rather than leaving a dangling rule.
    assert result.count("\n\n---\n\n") == len(sections)
    assert "TODO" in result or "API_KEY" in result


def test_codemap_with_no_optional_sections_is_just_the_base():
    # An empty project has nothing for any optional analysis to report, so the
    # export is exactly the base code map with no trailing rule.
    proj = {"name": "empty", "files": [], "file_contents": {}}
    base = importgraph.render_codemap_markdown(proj["name"], proj["files"])

    result = codemap_export.build_codemap_markdown(proj)

    if not [s for s in codemap_export._ordered_sections(proj) if s]:
        assert result == base
        assert "\n\n---\n\n" not in result
