"""Tests for filename meanings (deterministic, no LLM)."""

from __future__ import annotations

from backend.services import filenames


def test_exact_well_known_names():
    init = filenames.explain_path("pkg/__init__.py")
    assert init is not None
    assert init["name"] == "__init__.py"
    assert init["kind"] == "包标记"
    assert "包" in init["explanation"]

    conftest = filenames.explain_path("tests/conftest.py")
    # conftest is an exact match and must win over the tests/ directory hint.
    assert conftest is not None
    assert conftest["kind"] == "测试配置"
    assert "pytest" in conftest["explanation"]


def test_exact_match_is_case_insensitive():
    # Dockerfile / README.md are conventionally cased; match regardless.
    assert filenames.explain_path("Dockerfile")["kind"] == "打包成镜像"
    assert filenames.explain_path("docker/DOCKERFILE")["kind"] == "打包成镜像"
    assert filenames.explain_path("README.md")["kind"] == "项目简介"


def test_stem_rules_for_test_files():
    for path in ("tests/test_user.py", "app/user_test.py", "src/foo.test.tsx", "src/foo.spec.ts"):
        result = filenames.explain_path(path)
        assert result is not None, path
        assert result["kind"] == "测试代码", path


def test_django_style_role_files():
    assert filenames.explain_path("app/models.py")["kind"] == "数据结构"
    assert filenames.explain_path("app/views.py")["kind"] == "页面/接口逻辑"
    assert filenames.explain_path("app/urls.py")["kind"] == "地址路由表"
    assert filenames.explain_path("app/serializers.py")["kind"] == "数据转换"


def test_stem_rule_beats_directory_hint():
    # A test_*.py inside migrations/ should read as a test file, not as a
    # database migration — the more specific stem rule wins.
    result = filenames.explain_path("db/migrations/test_apply.py")
    assert result["kind"] == "测试代码"


def test_directory_hint_when_name_is_generic():
    # A generic name under migrations/ falls through to the directory hint.
    result = filenames.explain_path("db/migrations/0001_initial.py")
    assert result is not None
    assert result["kind"] == "数据库变更"


def test_extension_fallback():
    assert filenames.explain_path("src/app.tsx")["kind"] == "React 组件"
    assert filenames.explain_path("scripts/run.sh")["kind"] == "脚本"
    assert filenames.explain_path("data/schema.sql")["kind"] == "数据库语句"
    # A plain .py with no convention falls back to the bare-extension note.
    assert filenames.explain_path("app/whatever.py")["kind"] == "Python 源码"


def test_unknown_and_empty_return_none():
    assert filenames.explain_path("") is None
    assert filenames.explain_path(None) is None  # type: ignore[arg-type]
    assert filenames.explain_path("mystery.xyz") is None
    assert filenames.explain_path("LICENSE-ish-but-not") is None


def test_result_shape_is_stable():
    result = filenames.explain_path("app/utils.py")
    assert set(result.keys()) == {"name", "kind", "explanation"}
    assert result["name"] == "utils.py"
    assert all(isinstance(v, str) and v for v in result.values())
