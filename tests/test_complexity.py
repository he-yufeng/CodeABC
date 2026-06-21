from backend.services.complexity import render_complexity_markdown, scan_complexity


def test_straight_line_file_is_not_flagged():
    files = {"flat.py": "x = 1\ny = 2\nprint(x + y)\n"}
    assert scan_complexity(files)["files"] == []


def test_counts_branches_and_functions():
    src = (
        "def f(a, b):\n"
        "    if a and b:\n"  # if (+1), and (+1)
        "        return 1\n"
        "    for i in range(a):\n"  # for (+1)
        "        pass\n"
        "    return 0\n"
    )
    result = scan_complexity({"f.py": src})
    assert result["total"] == 1
    entry = result["files"][0]
    # base 1 + function 1 + if 1 + and 1 + for 1 == 5
    assert entry["complexity"] == 5
    assert entry["functions"] == 1


def test_ranks_more_complex_files_first():
    simple = "def g():\n    if True:\n        return 1\n"
    gnarly = "def h(x):\n" + "".join(f"    if x == {i}:\n        return {i}\n" for i in range(6))
    result = scan_complexity({"simple.py": simple, "gnarly.py": gnarly})
    assert [f["path"] for f in result["files"]] == ["gnarly.py", "simple.py"]
    assert result["files"][0]["complexity"] > result["files"][1]["complexity"]


def test_comprehension_filters_count():
    src = "vals = [x for x in items if x > 0 if x < 10]\n"  # for (+1) + two ifs (+2)
    entry = scan_complexity({"c.py": src})["files"][0]
    assert entry["complexity"] == 4  # base 1 + for 1 + 2 filters


def test_non_python_and_unparseable_files_are_skipped():
    files = {
        "data.json": '{"if": "for while and or"}',
        "broken.py": "def oops(:\n    pass\n",  # syntax error
        "ok.py": "if a:\n    pass\n",
    }
    result = scan_complexity(files)
    assert [f["path"] for f in result["files"]] == ["ok.py"]


def test_render_markdown_or_empty():
    assert render_complexity_markdown("x", {"files": []}) == ""
    md = render_complexity_markdown("Demo", scan_complexity({"m.py": "if a:\n    pass\n"}))
    assert "逻辑复杂度" in md and "`m.py`" in md
