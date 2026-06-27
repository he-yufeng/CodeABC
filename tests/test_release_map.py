from backend.services.release_map import find_release_info, render_release_markdown


def test_pyproject_semver_is_the_authoritative_version():
    data = find_release_info({"pyproject.toml": '[project]\nname = "foo"\nversion = "1.4.2"\n'})
    assert data["version"] == "1.4.2"
    assert data["version_source_kind"] == "pyproject"
    assert data["version_source"] == "pyproject.toml"
    assert data["scheme"] == "semver"
    assert data["dynamic_from_vcs"] is False


def test_zerover_is_called_out_as_pre_1_0():
    data = find_release_info({"pyproject.toml": 'version = "0.3.1"\n'})
    assert data["scheme"] == "zerover"
    assert "0." in data["version"]


def test_calver_scheme():
    data = find_release_info({"pyproject.toml": 'version = "2026.6.1"\n'})
    assert data["scheme"] == "calver"


def test_prerelease_without_separator_is_detected():
    data = find_release_info({"pyproject.toml": 'version = "1.0.0rc1"\n'})
    assert data["scheme"] == "prerelease"


def test_prerelease_with_dev_suffix():
    data = find_release_info({"pyproject.toml": 'version = "2.1.0.dev3"\n'})
    assert data["scheme"] == "prerelease"


def test_package_json_version():
    data = find_release_info({"package.json": '{\n  "name": "x",\n  "version": "3.2.1"\n}\n'})
    assert data["version"] == "3.2.1"
    assert data["version_source_kind"] == "package-json"


def test_pyproject_wins_over_package_json():
    data = find_release_info(
        {
            "pyproject.toml": 'version = "9.9.9"\n',
            "package.json": '{"version": "1.0.0"}\n',
        }
    )
    assert data["version"] == "9.9.9"
    assert data["version_source_kind"] == "pyproject"


def test_dynamic_version_from_git_tags():
    data = find_release_info(
        {
            "pyproject.toml": (
                '[project]\nname = "foo"\ndynamic = ["version"]\n[tool.setuptools_scm]\n'
            )
        }
    )
    assert data["dynamic_from_vcs"] is True
    assert data["version"] == ""
    assert any("git tag" in n for n in data["notes"])


def test_version_file():
    data = find_release_info({"VERSION": "v2.5.0\n"})
    assert data["version"] == "2.5.0"
    assert data["version_source_kind"] == "version-file"


def test_dunder_version_in_python_source():
    data = find_release_info({"pkg/__init__.py": '__version__ = "0.9.0"\n'})
    assert data["version"] == "0.9.0"
    assert data["version_source_kind"] == "dunder"


def test_changelog_keepachangelog_style():
    data = find_release_info(
        {
            "CHANGELOG.md": (
                "# Changelog\n\nThe format is based on "
                "[Keep a Changelog](https://keepachangelog.com).\n\n## [Unreleased]\n"
            )
        }
    )
    assert data["changelog_path"] == "CHANGELOG.md"
    assert data["changelog_style"] == "keepachangelog"


def test_changelog_versioned_style():
    data = find_release_info(
        {"CHANGELOG.md": "# Changelog\n\n## [1.2.0] - 2026-01-01\n### Added\n- thing\n"}
    )
    assert data["changelog_style"] == "versioned"


def test_no_changelog_is_noted():
    data = find_release_info({"pyproject.toml": 'version = "1.0.0"\n'})
    assert data["changelog_style"] == "none"
    assert any("更新日志" in n for n in data["notes"])


def test_release_automation_pypi_on_tag_push():
    workflow = (
        "name: release\n"
        "on:\n"
        "  push:\n"
        "    tags:\n"
        "      - 'v*'\n"
        "jobs:\n"
        "  build:\n"
        "    steps:\n"
        "      - uses: pypa/gh-action-pypi-publish@release/v1\n"
    )
    data = find_release_info({".github/workflows/release.yml": workflow})
    assert "PyPI" in data["publish_targets"]
    pypi = [a for a in data["automation"] if a["target"] == "PyPI"]
    assert pypi and pypi[0]["trigger"] == "tag-push"
    assert pypi[0]["line"] >= 1


def test_release_automation_npm_and_github_release():
    workflow = (
        "on:\n"
        "  release:\n"
        "    types: [published]\n"
        "jobs:\n"
        "  publish:\n"
        "    steps:\n"
        "      - run: npm publish\n"
        "      - uses: softprops/action-gh-release@v2\n"
    )
    data = find_release_info({".github/workflows/publish.yml": workflow})
    assert "npm" in data["publish_targets"]
    assert "GitHub Release" in data["publish_targets"]
    npm = [a for a in data["automation"] if a["target"] == "npm"][0]
    assert npm["trigger"] == "release"


def test_render_returns_empty_when_nothing_found():
    data = find_release_info({"README.md": "# hello\n"})
    assert render_release_markdown("demo", data) == ""


def test_render_includes_version_and_pipeline():
    data = find_release_info(
        {
            "pyproject.toml": 'version = "1.4.2"\n',
            "CHANGELOG.md": "# Changelog\n\n## [1.4.2]\n- fix\n",
            ".github/workflows/release.yml": (
                "on:\n  push:\n    tags: ['v*']\n    steps:\n      - run: twine upload dist/*\n"
            ),
        }
    )
    md = render_release_markdown("demo", data)
    assert "demo — 版本与发布地图" in md
    assert "1.4.2" in md
    assert "PyPI" in md
    assert "CHANGELOG.md" in md
