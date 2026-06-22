"""Tests for the package-purpose dictionary (deterministic, no LLM)."""

from __future__ import annotations

from backend.services import package_purposes


def test_known_packages_have_purposes():
    assert "API" in package_purposes.explain_package("fastapi")
    assert package_purposes.explain_package("pandas")
    assert package_purposes.explain_package("react")
    assert package_purposes.explain_package("pytest")


def test_lookup_is_case_insensitive():
    assert package_purposes.explain_package("FastAPI") == package_purposes.explain_package(
        "fastapi"
    )
    assert package_purposes.explain_package("NumPy") == package_purposes.explain_package("numpy")


def test_extras_suffix_is_stripped():
    # "uvicorn[standard]" should resolve to the same note as "uvicorn".
    assert package_purposes.explain_package(
        "uvicorn[standard]"
    ) == package_purposes.explain_package("uvicorn")


def test_aliases_resolve_to_canonical_note():
    assert package_purposes.explain_package("sklearn") == package_purposes.explain_package(
        "scikit-learn"
    )
    assert package_purposes.explain_package("bs4") == package_purposes.explain_package(
        "beautifulsoup4"
    )
    assert package_purposes.explain_package("yaml") == package_purposes.explain_package("pyyaml")


def test_unknown_and_empty_return_none():
    assert package_purposes.explain_package("") is None
    assert package_purposes.explain_package(None) is None  # type: ignore[arg-type]
    assert package_purposes.explain_package("some-obscure-internal-pkg") is None


def test_scan_dependencies_attaches_purpose():
    # End-to-end: a requirements file with a known and an unknown package.
    from backend.services import dependencies

    contents = {"requirements.txt": "fastapi==0.110\nsome-obscure-internal-pkg==1.0\n"}
    result = dependencies.scan_dependencies(contents)
    by_name = {d["name"]: d for d in result["dependencies"]}
    assert by_name["fastapi"]["purpose"]  # known package carries a note
    assert by_name["some-obscure-internal-pkg"]["purpose"] is None  # unknown stays None
