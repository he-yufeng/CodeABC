from backend.services.dependencies import render_dependencies_markdown, scan_dependencies


def _names(data, kind=None):
    return {d["name"] for d in data["dependencies"] if kind is None or d["kind"] == kind}


def test_requirements_txt_parses_name_and_version():
    files = {"requirements.txt": "requests>=2.0\nrich==13.7.0\n# a comment\n\n-r other.txt\n"}
    data = scan_dependencies(files)
    assert _names(data) == {"requests", "rich"}
    req = next(d for d in data["dependencies"] if d["name"] == "requests")
    assert req["version"] == ">=2.0"
    assert req["kind"] == "runtime"
    assert req["manifest"] == "requirements.txt"


def test_requirements_dev_file_is_marked_dev():
    files = {"requirements-dev.txt": "pytest>=8\nruff\n"}
    data = scan_dependencies(files)
    assert _names(data, "dev") == {"pytest", "ruff"}


def test_requirements_drops_extras_and_env_markers():
    files = {"requirements.txt": 'uvicorn[standard]>=0.30 ; python_version >= "3.10"\n'}
    dep = scan_dependencies(files)["dependencies"][0]
    assert dep["name"] == "uvicorn"
    assert dep["version"] == ">=0.30"


def test_pyproject_pep621_runtime_and_optional():
    files = {
        "pyproject.toml": (
            "[project]\nname = 'demo'\n"
            'dependencies = ["fastapi>=0.110", "requests[security]>=2,<3"]\n\n'
            "[project.optional-dependencies]\n"
            'dev = ["pytest", "ruff>=0.5"]\n'
        )
    }
    data = scan_dependencies(files)
    # the extras bracket inside the quoted string must not truncate the array
    assert _names(data, "runtime") == {"fastapi", "requests"}
    assert _names(data, "optional") == {"pytest", "ruff"}


def test_pyproject_poetry_skips_python_constraint():
    files = {
        "pyproject.toml": (
            '[tool.poetry.dependencies]\npython = "^3.10"\nhttpx = "^0.27"\n\n'
            '[tool.poetry.dev-dependencies]\nmypy = "^1.10"\n'
        )
    }
    data = scan_dependencies(files)
    assert "python" not in _names(data)
    assert _names(data, "runtime") == {"httpx"}
    assert _names(data, "dev") == {"mypy"}


def test_setup_cfg_install_requires_multiline():
    files = {
        "setup.cfg": ("[options]\ninstall_requires =\n    click>=8\n    pyyaml\npackages = find:\n")
    }
    data = scan_dependencies(files)
    assert _names(data, "runtime") == {"click", "pyyaml"}


def test_pipfile_packages_and_dev():
    files = {"Pipfile": '[packages]\nflask = "*"\n\n[dev-packages]\nblack = "==24.1.0"\n'}
    data = scan_dependencies(files)
    flask = next(d for d in data["dependencies"] if d["name"] == "flask")
    assert flask["kind"] == "runtime"
    assert flask["version"] == ""  # "*" is normalized to no constraint
    assert _names(data, "dev") == {"black"}


def test_package_json_runtime_and_dev():
    files = {
        "package.json": (
            '{"name": "ui", "dependencies": {"react": "^19.0.0"}, '
            '"devDependencies": {"vite": "^5.0.0"}}'
        )
    }
    data = scan_dependencies(files)
    assert _names(data, "runtime") == {"react"}
    assert _names(data, "dev") == {"vite"}


def test_malformed_package_json_is_ignored():
    assert scan_dependencies({"package.json": "{ not json"})["dependencies"] == []


def test_runtime_role_wins_over_dev_for_same_package():
    files = {
        "requirements.txt": "shared>=1\n",
        "requirements-dev.txt": "shared>=1\n",
    }
    data = scan_dependencies(files)
    shared = [d for d in data["dependencies"] if d["name"] == "shared"]
    assert len(shared) == 1  # de-duplicated
    assert shared[0]["kind"] == "runtime"  # strongest role kept


def test_manifests_are_reported_and_deps_sorted_by_kind():
    files = {
        "requirements.txt": "zlib-pkg\nalib\n",
        "package.json": '{"devDependencies": {"jest": "^29"}}',
    }
    data = scan_dependencies(files)
    assert set(data["manifests"]) == {"requirements.txt", "package.json"}
    # runtime deps come before dev deps in the ranked list
    kinds = [d["kind"] for d in data["dependencies"]]
    assert kinds == sorted(kinds, key=lambda k: {"runtime": 0, "dev": 1, "optional": 2}[k])


def test_render_markdown_groups_by_kind_or_empty():
    assert render_dependencies_markdown("x", {"dependencies": []}) == ""
    files = {"requirements.txt": "requests>=2\n", "requirements-dev.txt": "pytest\n"}
    md = render_dependencies_markdown("Demo", scan_dependencies(files))
    assert "外部依赖清单" in md
    assert "运行依赖" in md and "**requests**" in md
    assert "开发依赖" in md and "**pytest**" in md
    assert "`requirements.txt`" in md
