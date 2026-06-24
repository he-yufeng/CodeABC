from backend.services import report_export


def _demo_project() -> dict:
    # Same tiny project shape the codemap export test uses: no git history, but
    # the file text carries a TODO and an env var so several sections fire.
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


def test_report_is_a_self_contained_html_document():
    html = report_export.build_report_html(_demo_project())

    # A complete, standalone page...
    assert html.startswith("<!doctype html>")
    assert "<title>demo — CodeABC report</title>" in html
    assert "</html>" in html.rstrip().splitlines()[-1] or html.rstrip().endswith("</html>")
    # ...with styling inlined and nothing fetched from the network.
    assert "<style>" in html
    assert "http://" not in html.split("</head>")[0].replace("rel=", "")
    assert "src=" not in html and "<link" not in html


def test_report_carries_the_same_analysis_as_the_codemap():
    html = report_export.build_report_html(_demo_project())

    # The deterministic findings (env var, tech-debt marker) reach the report.
    assert "API_KEY" in html
    assert "TODO" in html
    # Markdown was rendered to real HTML, not dumped verbatim.
    assert "<h1>" in html and "<li>" in html
    assert "\n# demo" not in html


def test_renderer_escapes_content_so_it_cannot_inject_markup():
    # A file path containing angle brackets must not become a live tag in the
    # exported file — the renderer escapes text before formatting it.
    proj = {
        "name": "x",
        "files": [{"path": "<script>evil.py", "content": "print(1)\n"}],
        "file_contents": {"<script>evil.py": "# TODO: <img src=x onerror=alert(1)>\n"},
    }

    html = report_export.build_report_html(proj)

    assert "<script>evil" not in html
    assert "<img src=x" not in html
    assert "&lt;script&gt;" in html or "&lt;img" in html


def test_markdown_renderer_handles_each_block_type():
    md = (
        "# Heading one\n\n"
        "> a quoted intro line\n\n"
        "## Heading two\n\n"
        "- top bullet with `code`\n"
        "  - nested bullet in **bold**\n\n"
        "| Col A | Col B |\n| --- | --- |\n| a | b |\n\n"
        "---\n\n"
        "a closing paragraph\n"
    )

    out = report_export._markdown_to_html(md)

    assert "<h1>Heading one</h1>" in out
    assert "<h2>Heading two</h2>" in out
    assert "<blockquote>a quoted intro line</blockquote>" in out
    assert "<code>code</code>" in out
    assert "<strong>bold</strong>" in out
    assert out.count("<ul>") == 2 and out.count("</ul>") == 2  # one level of nesting
    assert "<table>" in out and "<th>Col A</th>" in out and "<td>a</td>" in out
    assert "<hr>" in out
    assert "<p>a closing paragraph</p>" in out


def test_empty_project_still_produces_a_valid_page():
    html = report_export.build_report_html({"name": "empty", "files": [], "file_contents": {}})

    assert html.startswith("<!doctype html>")
    assert "<title>empty — CodeABC report</title>" in html
    assert html.rstrip().endswith("</html>")
