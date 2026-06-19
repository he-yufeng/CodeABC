"""Tests for the terminology dictionary (deterministic, no LLM)."""

from __future__ import annotations

from backend.services import glossary


def test_lookup_case_insensitive():
    assert glossary.lookup("API")
    assert glossary.lookup("api") == glossary.lookup("Api")
    assert glossary.lookup("not-a-real-term") is None


def test_scan_finds_terms_with_definitions():
    code = "async def fetch():\n    await api.get()  # uses a cache\n"
    terms = {e["term"] for e in glossary.scan_terms(code)}
    assert {"async", "await", "api", "cache"} <= terms
    for entry in glossary.scan_terms(code):
        assert entry["definition"]  # every hit carries a definition


def test_whole_word_matching_no_substrings():
    # "api" must not light up inside "rapid"; "lock" not inside "blockchain"
    terms = {e["term"] for e in glossary.scan_terms("rapid blockchain therapist")}
    assert "api" not in terms
    assert "lock" not in terms


def test_results_deduped_and_sorted():
    code = "cache cache CACHE\nasync async\n"
    result = glossary.scan_terms(code)
    names = [e["term"] for e in result]
    assert names == sorted(names)  # alphabetical
    assert len(names) == len(set(names))  # de-duplicated
    assert names == ["async", "cache"]


def test_phrase_terms_matched():
    terms = {e["term"] for e in glossary.scan_terms("watch out for a race condition here")}
    assert "race condition" in terms
    # flexible whitespace between phrase words
    assert any(
        e["term"] == "dependency injection"
        for e in glossary.scan_terms("we use dependency   injection")
    )


def test_empty_text_returns_empty():
    assert glossary.scan_terms("") == []
    assert glossary.scan_terms(None) == []  # type: ignore[arg-type]
